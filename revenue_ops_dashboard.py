import streamlit as st
import pandas as pd
import numpy as np
import os
import json
import requests
import feedparser
from datetime import datetime, timedelta
from google import genai
import random

st.set_page_config(page_title="Revenue Ops Intelligence", page_icon="📊", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
    html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
    .metric-card { background:white; border:1px solid #e2e8f0; border-radius:10px; padding:1.25rem 1.5rem; }
    .metric-label { font-size:0.75rem; font-weight:600; letter-spacing:0.08em; text-transform:uppercase; color:#64748b; margin-bottom:0.4rem; }
    .metric-value { font-size:2rem; font-weight:600; color:#0f172a; line-height:1; font-family:'IBM Plex Mono',monospace; }
    .metric-delta { font-size:0.8rem; margin-top:0.3rem; }
    .metric-delta.good { color:#16a34a; } .metric-delta.bad { color:#dc2626; } .metric-delta.neutral { color:#64748b; }
    .metric-tooltip { font-size:0.78rem; color:#64748b; margin-top:0.5rem; border-top:1px solid #f1f5f9; padding-top:0.5rem; line-height:1.5; font-style:italic; }
    .section-card { background:white; border:1px solid #e2e8f0; border-radius:10px; padding:1.5rem; margin-bottom:1rem; }
    .section-title { font-size:0.8rem; font-weight:600; letter-spacing:0.08em; text-transform:uppercase; color:#64748b; margin-bottom:1rem; padding-bottom:0.75rem; border-bottom:1px solid #f1f5f9; }
    .risk-badge { display:inline-block; padding:3px 10px; border-radius:20px; font-size:0.72rem; font-weight:600; }
    .risk-high { background:#fee2e2; color:#991b1b; }
    .risk-med { background:#fef3c7; color:#92400e; }
    .risk-low { background:#dcfce7; color:#166534; }
    .insight-row { display:flex; align-items:flex-start; gap:0.75rem; padding:0.75rem 0; border-bottom:1px solid #f1f5f9; font-size:0.9rem; }
    .insight-row:last-child { border-bottom:none; }
    .progress-bar-bg { background:#f1f5f9; border-radius:4px; height:8px; width:100%; margin-top:6px; }
    .progress-bar-fill { height:8px; border-radius:4px; }
    .news-card { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:0.9rem 1rem; margin-bottom:0.6rem; }
    .news-tag { display:inline-block; font-size:0.7rem; font-weight:600; padding:2px 8px; border-radius:20px; margin-right:4px; background:#e0f2fe; color:#0369a1; }
    .info-box { background:#f0f9ff; border:1px solid #bae6fd; border-radius:8px; padding:0.75rem 1rem; font-size:0.82rem; color:#0369a1; margin-bottom:0.75rem; }
    .warn-box { background:#fefce8; border:1px solid #fde047; border-radius:8px; padding:0.75rem 1rem; font-size:0.82rem; color:#713f12; }
    .module-card { background:white; border:1px solid #e2e8f0; border-radius:10px; padding:1.25rem; text-align:center; }
    .stButton > button { background:#0f172a; color:white; border:none; border-radius:8px; padding:0.5rem 1.25rem; font-family:'IBM Plex Sans',sans-serif; font-size:0.9rem; font-weight:500; }
    .stButton > button:hover { background:#1e293b; }
    .upload-hint { background:#f8fafc; border:1.5px dashed #cbd5e1; border-radius:10px; padding:2rem; text-align:center; color:#64748b; font-size:0.9rem; }
    #MainMenu { visibility:hidden; } footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

# ── Gemini ────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        st.error("GEMINI_API_KEY not found.")
        st.stop()
    return genai.Client(api_key=key)

client = get_client()
MODEL = "gemini-2.5-flash"

# ── Config ────────────────────────────────────────────────────────────────────
REGIONS = {
    "Malaysia": {"geo":"MY","worldbank":"MYS"},
    "Singapore": {"geo":"SG","worldbank":"SGP"},
    "Vietnam": {"geo":"VN","worldbank":"VNM"},
    "Indonesia": {"geo":"ID","worldbank":"IDN"},
    "Thailand": {"geo":"TH","worldbank":"THA"},
}
INDUSTRIES = {
    "F&B / FMCG": {"keywords":["food","beverage","FMCG","consumer goods","grocery"],"worldbank_indicators":["NY.GDP.MKTP.KD.ZG","FP.CPI.TOTL.ZG"],"dso_benchmark":45,"inv_benchmark":40},
    "Electronics Manufacturing": {"keywords":["electronics","semiconductor","manufacturing","supply chain"],"worldbank_indicators":["NY.GDP.MKTP.KD.ZG","NE.EXP.GNFS.ZS"],"dso_benchmark":50,"inv_benchmark":50},
    "Medical / Healthcare": {"keywords":["medical","healthcare","pharmaceutical","hygiene"],"worldbank_indicators":["NY.GDP.MKTP.KD.ZG","SH.XPD.CHEX.GD.ZS"],"dso_benchmark":40,"inv_benchmark":45},
    "Automotive / Industrial": {"keywords":["automotive","industrial","machinery","logistics"],"worldbank_indicators":["NY.GDP.MKTP.KD.ZG","NE.EXP.GNFS.ZS"],"dso_benchmark":55,"inv_benchmark":55},
    "Retail / E-Commerce": {"keywords":["retail","e-commerce","online shopping","consumer"],"worldbank_indicators":["NY.GDP.MKTP.KD.ZG","FP.CPI.TOTL.ZG"],"dso_benchmark":30,"inv_benchmark":25},
}
RSS_FEEDS = {
    "Malaysia": [("The Star Business","https://www.thestar.com.my/rss/business"),("The Edge Malaysia","https://theedgemalaysia.com/feed")],
    "Singapore": [("Channel NewsAsia","https://www.channelnewsasia.com/rssfeeds/8395986"),("Straits Times","https://www.straitstimes.com/news/business/rss.xml")],
    "Vietnam": [("VnExpress Business","https://e.vnexpress.net/rss/business.rss")],
    "Indonesia": [("Jakarta Post","https://www.thejakartapost.com/feed/category/business")],
    "Thailand": [("Bangkok Post","https://www.bangkokpost.com/rss/data/business.xml")],
}
WB_LABELS = {"NY.GDP.MKTP.KD.ZG":"GDP Growth Rate (%)","FP.CPI.TOTL.ZG":"Inflation Rate (CPI %)","NE.EXP.GNFS.ZS":"Exports (% of GDP)","SH.XPD.CHEX.GD.ZS":"Health Expenditure (% of GDP)"}
TIPS = {
    "accuracy": "How close forecasts are to actual demand. Target: 85–90%. Formula: 100 − MAPE. Source: Kleen-Pak CFO — no accuracy tracking was in place.",
    "mape": "Mean Absolute Percentage Error — average % gap between forecast and actual. Lower = better. Industry target: <15%.",
    "bias": "Systematic over/under-forecasting. Positive = over-forecasting (excess inventory). Negative = under-forecasting (stockouts). Target: ±5%.",
    "dso": "Days Sales Outstanding — average days to collect payment after invoicing. Source: Kleen-Pak CFO flagged DSO as top pain point.",
    "leakage": "Revenue lost through errors, disputes & deductions. Source: Module 4.4 of Normality SPAN pain point analysis.",
    "error_rate": "% of invoices with errors. Target: <2%. Source: Kleen-Pak — portal submission failures cause payment delays.",
    "dispute_rate": "% of invoices disputed. High rate signals pricing/contract mismatches. Target: <5%. Source: Module 4.2.",
    "ccc": "Cash Conversion Cycle = DSO + Inventory Days − DPO. Days cash is tied up in operations. Lower = healthier. Source: Sime Darby CIO — working capital visibility was a CFO priority.",
}

def tip(key):
    return f"<div class='metric-tooltip'>ℹ️ {TIPS.get(key,'')}</div>"

# ── Fetchers ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_news(region, industry):
    kws = [k.lower() for k in INDUSTRIES[industry]["keywords"]]
    arts = []
    for src, url in RSS_FEEDS.get(region, []):
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:25]:
                t = e.get("title",""); s = e.get("summary","")
                matched = [k for k in kws if k in (t+" "+s).lower()]
                if matched:
                    arts.append({"title":t,"source":src,"published":e.get("published","")[:16],"keywords":matched[:2]})
        except: pass
    return arts[:10]

@st.cache_data(ttl=86400)
def fetch_wb(region, industry):
    c = REGIONS[region]["worldbank"]; res = {}
    for ind in INDUSTRIES[industry]["worldbank_indicators"]:
        try:
            r = requests.get(f"https://api.worldbank.org/v2/country/{c}/indicator/{ind}?format=json&mrv=5&per_page=5", timeout=8)
            if r.status_code == 200:
                d = r.json()
                if len(d)>1 and d[1]:
                    s = [{"year":x["date"],"value":round(x["value"],2)} for x in d[1] if x["value"] is not None]
                    if s: res[WB_LABELS.get(ind,ind)] = sorted(s,key=lambda x:x["year"])
        except: pass
    return res

@st.cache_data(ttl=3600)
def fetch_gt(keywords, region):
    geo = REGIONS[region]["geo"]
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl='en-US',tz=480,timeout=(10,25))
        kws = keywords[:3]
        pt.build_payload(kws,timeframe='today 1-m',geo=geo)
        df = pt.interest_over_time()
        if df.empty: return {"error":"No data returned.","data":{}}
        df = df.drop(columns=["isPartial"],errors="ignore")
        return {"data":{k:[{"date":str(d.date()),"value":int(v)} for d,v in zip(df.index,df[k])] for k in kws if k in df.columns}}
    except ImportError: return {"error":"Run: pip3 install pytrends","data":{}}
    except Exception as e: return {"error":str(e),"data":{}}

# ── Analytics ─────────────────────────────────────────────────────────────────
def calc_forecast(df):
    df = df.copy()
    df["MAPE"] = (df["Actual_Units"]-df["Forecast_Units"]).abs()/df["Actual_Units"].replace(0,np.nan)*100
    df["Bias"] = (df["Actual_Units"]-df["Forecast_Units"])/df["Actual_Units"].replace(0,np.nan)*100
    mape = df["MAPE"].mean()
    return {"accuracy":round(max(0,100-mape),1),"mape":round(mape,1),"bias":round(df["Bias"].mean(),1),
            "sku":df.groupby("SKU").agg(MAPE=("MAPE","mean"),Bias=("Bias","mean"),Accuracy=("MAPE",lambda x:max(0,100-x.mean()))).reset_index().round(1),
            "monthly":df}

def calc_o2c(df, industry):
    bench = INDUSTRIES[industry]["dso_benchmark"]
    dso = df["DSO_Days"].mean()
    err = df.get("Invoice_Errors",pd.Series([0]*len(df))).mean()*100
    disp = df.get("Disputed",pd.Series([0]*len(df))).mean()*100
    rev = df["Invoice_Amount_USD"].sum()
    ld = rev*0.018; ie = rev*(err/100)*0.025; dd = rev*(disp/100)*0.05; ed = rev*0.008
    cust = df.groupby("Customer")["DSO_Days"].mean().reset_index()
    cust.columns = ["Customer","Avg_DSO"]
    cust["Risk"] = cust["Avg_DSO"].apply(lambda x: "🔴 High" if x>bench*1.4 else ("🟡 Medium" if x>bench*1.1 else "🟢 Low"))
    cust["Trend"] = cust["Avg_DSO"].apply(lambda x: "Overdue risk" if x>bench*1.4 else ("Watch" if x>bench*1.1 else "On track"))
    return {"dso":round(dso,1),"bench":bench,"gap":round(dso-bench,1),"err":round(err,1),"disp":round(disp,1),
            "rev":round(rev,0),"leak_total":round(ld+ie+dd+ed,0),"leak_disc":round(ld,0),"leak_inv":round(ie,0),
            "leak_disp":round(dd,0),"leak_ded":round(ed,0),"cust":cust.sort_values("Avg_DSO",ascending=False).round(1)}

def calc_wc(om, industry, inv_days, dpo):
    dso = om["dso"]; bench_dso = om["bench"]
    ccc = dso + inv_days - dpo
    bench_ccc = bench_dso + INDUSTRIES[industry]["inv_benchmark"] - 30
    gap = ccc - bench_ccc
    score = max(0,min(100,round(100-(gap/max(bench_ccc,1))*50)))
    return {"ccc":round(ccc,1),"bench":round(bench_ccc,1),"dso":dso,"inv":inv_days,"dpo":dpo,
            "gap":round(gap,1),"score":score,"health":"Good" if score>=70 else "At Risk" if score>=45 else "Critical"}

def calc_modules(fm, om):
    return {
        "Demand": {"score":min(100,round(fm["accuracy"]*0.7+max(0,20-abs(fm["bias"]))*1.5)),"pain":"Forecast accuracy & bias"},
        "Order Mgmt": {"score":max(0,min(100,round(100-om["err"]*5-om["disp"]*3))),"pain":"Entry errors & validation gaps"},
        "Fulfilment": {"score":max(0,min(100,round(100-(om["gap"] if om["gap"]>0 else 0)*1.2))),"pain":"DSO lag & delivery accuracy"},
        "Billing": {"score":max(0,min(100,round(100-om["err"]*8-om["disp"]*4))),"pain":"Invoice disputes & rebates"},
        "Working Capital": {"score":max(0,min(100,round(100-(om["leak_total"]/max(om["rev"],1))*300))),"pain":"Cash locked in DSO & inventory"},
    }

def get_ai(fm, om, wc, region, industry):
    prompt = f"""Revenue Operations expert for {industry} in {region}.
FORECAST: Accuracy {fm['accuracy']}%, MAPE {fm['mape']}%, Bias {fm['bias']:+.1f}%
O2C: DSO {om['dso']}d (bench {om['bench']}d), Leakage USD {om['leak_total']:,.0f}, Errors {om['err']}%, Disputes {om['disp']}%
WORKING CAPITAL: CCC {wc['ccc']}d (bench {wc['bench']}d), Score {wc['score']}/100
Context: Real interviews with SEA manufacturer CFOs. Key pain: no forecast tracking, portal submission failures, non-binding customer forecasts, manual rebates.
Return ONLY JSON (no markdown):
{{"overall_health":"Good|At Risk|Critical","health_score":<int>,
"top_risks":[{{"risk":"...","severity":"High|Medium|Low","impact":"...","module":"..."}},{{"risk":"...","severity":"High|Medium|Low","impact":"...","module":"..."}},{{"risk":"...","severity":"High|Medium|Low","impact":"...","module":"..."}}],
"quick_wins":[{{"action":"...","timeline":"...","expected_impact":"...","source":"Interview|Excel|Benchmark"}},{{"action":"...","timeline":"...","expected_impact":"...","source":"Interview|Excel|Benchmark"}},{{"action":"...","timeline":"...","expected_impact":"...","source":"Interview|Excel|Benchmark"}}],
"forecast_insight":"...","o2c_insight":"...","wc_insight":"...","executive_summary":"..."}}"""
    r = client.models.generate_content(model=MODEL, contents=prompt)
    text = r.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(text)

def get_trend_ai(region, industry, news, wb, gt):
    nt = "\n".join([f"- [{a['source']}] {a['title']}" for a in news[:8]]) or "None."
    wt = "\n".join([f"- {l}: {s[-1]['value']} ({s[-1]['year']})" for l,s in wb.items() if s]) or "None."
    gtt = "\n".join([f"- '{k}': avg {round(sum(p['value'] for p in s)/len(s),1)}/100" for k,s in gt.get("data",{}).items() if s]) or gt.get("error","Unavailable.")
    prompt = f"""Supply Chain analyst for {region}'s {industry} sector. Analyse ONLY the data below. Cite source for every claim. Never invent.
NEWS: {nt}\nWORLD BANK: {wt}\nGOOGLE TRENDS: {gtt}
Provide: 1) 3-sentence summary with citations 2) Top 3 demand signals (cite source) 3) Top 2 supply risks 4) One forecasting adjustment backed by data."""
    r = client.models.generate_content(model=MODEL, contents=prompt)
    return r.text.strip()

# ── Sample data ───────────────────────────────────────────────────────────────
def sample_fc():
    np.random.seed(42)
    months = pd.date_range("2024-01-01",periods=12,freq="MS")
    skus = ["WW-MED-001","WW-FMCG-002","WW-FMCG-003","WW-MED-004"]
    rows = []
    for sku in skus:
        base = np.random.randint(800,3000)
        for m in months:
            actual = int(base*(1+0.15*np.sin(m.month)+np.random.normal(0,0.1)))
            rows.append({"Month":m.strftime("%Y-%m"),"SKU":sku,"Actual_Units":actual,"Forecast_Units":int(actual*(1+np.random.normal(0,0.18)))})
    return pd.DataFrame(rows)

def sample_o2c():
    np.random.seed(42)
    custs = ["Lotus's MY","AEON Malaysia","Guardian","Watsons","Parkson","Cold Storage"]
    rows = []
    for i in range(60):
        od = datetime(2024,1,1)+timedelta(days=random.randint(0,364))
        inv = od+timedelta(days=random.randint(1,5))
        pay = inv+timedelta(days=random.randint(15,120))
        rows.append({"Order_ID":f"ORD-{1000+i}","Customer":random.choice(custs),"Order_Date":od.strftime("%Y-%m-%d"),
                     "Invoice_Date":inv.strftime("%Y-%m-%d"),"Payment_Date":pay.strftime("%Y-%m-%d"),
                     "Invoice_Amount_USD":round(random.uniform(5000,80000),2),"DSO_Days":(pay-inv).days,
                     "Invoice_Errors":random.choice([0,0,0,1]),"Disputed":random.choice([0,0,0,0,1])})
    return pd.DataFrame(rows)

# ── Session state ─────────────────────────────────────────────────────────────
DEFS = {"fc_df":None,"o2c_df":None,"fc_hash":None,"o2c_hash":None,"fc_m":None,"o2c_m":None,
        "wc_m":None,"mod_s":None,"ai":None,"done":False,"tnews":None,"twb":None,"tgt":None,
        "tai":None,"tfetched":False,"region":"Malaysia","industry":"F&B / FMCG"}
for k,v in DEFS.items():
    if k not in st.session_state: st.session_state[k] = v

def reset():
    for k,v in DEFS.items(): st.session_state[k] = v

# ── Header ────────────────────────────────────────────────────────────────────
h1,h2,h3,h4,h5 = st.columns([2,1,1,0.65,0.65])
with h1:
    st.markdown("## Revenue Ops Intelligence")
    st.markdown("<p style='color:#64748b;margin-top:-0.5rem;font-size:0.9rem;'>Demand · O2C · Revenue Leakage · Working Capital · Market Intel</p>", unsafe_allow_html=True)
with h2:
    region = st.selectbox("🌏 Region",list(REGIONS.keys()),index=list(REGIONS.keys()).index(st.session_state.region))
    st.session_state.region = region
with h3:
    industry = st.selectbox("🏭 Industry",list(INDUSTRIES.keys()),index=list(INDUSTRIES.keys()).index(st.session_state.industry))
    st.session_state.industry = industry
with h4:
    st.markdown("<br>",unsafe_allow_html=True)
    if st.button("📊 Sample"):
        st.session_state.fc_df=sample_fc(); st.session_state.o2c_df=sample_o2c()
        st.session_state.fc_hash="s"; st.session_state.o2c_hash="s"; st.session_state.done=False; st.rerun()
with h5:
    st.markdown("<br>",unsafe_allow_html=True)
    if st.button("🔄 Reset"):
        reset(); st.rerun()

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────
t1,t2,t3,t4,t5,t6 = st.tabs(["📥 Data Input","📦 Demand Forecasting","💰 Order-to-Cash","💧 Revenue Leakage","🏦 Working Capital","🌐 Market Intel & AI"])

# ── TAB 1: DATA INPUT ─────────────────────────────────────────────────────────
with t1:
    st.markdown('<div style="font-size:1.3rem;font-weight:600;color:#0f172a;margin-bottom:0.25rem">Upload Your Data</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.9rem;color:#64748b;margin-bottom:1.5rem">Upload CSVs or load sample data. Both files needed to run analysis.</div>', unsafe_allow_html=True)

    c1,c2 = st.columns(2)
    with c1:
        st.markdown('<div class="section-card"><div class="section-title">📦 Demand Forecast CSV</div>', unsafe_allow_html=True)
        st.markdown("**Required:** `Month` · `SKU` · `Actual_Units` · `Forecast_Units`")
        uf = st.file_uploader("Forecast",type=["csv"],key="fc_up",label_visibility="collapsed")
        if uf:
            try:
                df = pd.read_csv(uf); h = str(hash(df.to_json()))
                req=["Month","SKU","Actual_Units","Forecast_Units"]; miss=[c for c in req if c not in df.columns]
                if not miss:
                    if h != st.session_state.fc_hash:
                        st.session_state.fc_df=df; st.session_state.fc_hash=h; st.session_state.done=False
                    st.success(f"✓ {len(df)} rows loaded")
                else: st.error(f"Missing: {miss}")
            except Exception as e: st.error(str(e))
        elif st.session_state.fc_df is not None: st.success(f"✓ {len(st.session_state.fc_df)} rows ready")
        else: st.markdown('<div class="upload-hint">Upload CSV or click 📊 Sample</div>',unsafe_allow_html=True)
        st.markdown("</div>",unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="section-card"><div class="section-title">💰 Order-to-Cash CSV</div>', unsafe_allow_html=True)
        st.markdown("**Required:** `Order_ID` · `Customer` · `Invoice_Amount_USD` · `DSO_Days`")
        uo = st.file_uploader("O2C",type=["csv"],key="o2c_up",label_visibility="collapsed")
        if uo:
            try:
                df = pd.read_csv(uo); h = str(hash(df.to_json()))
                req=["Order_ID","Customer","Invoice_Amount_USD","DSO_Days"]; miss=[c for c in req if c not in df.columns]
                if not miss:
                    if h != st.session_state.o2c_hash:
                        st.session_state.o2c_df=df; st.session_state.o2c_hash=h; st.session_state.done=False
                    st.success(f"✓ {len(df)} rows loaded")
                else: st.error(f"Missing: {miss}")
            except Exception as e: st.error(str(e))
        elif st.session_state.o2c_df is not None: st.success(f"✓ {len(st.session_state.o2c_df)} rows ready")
        else: st.markdown('<div class="upload-hint">Upload CSV or click 📊 Sample</div>',unsafe_allow_html=True)
        st.markdown("</div>",unsafe_allow_html=True)

    st.markdown('<div class="section-card"><div class="section-title">🏦 Working Capital Inputs (Optional)</div>', unsafe_allow_html=True)
    st.markdown('<div class="info-box">These power the Working Capital tab. Use defaults if you don\'t have exact figures.</div>',unsafe_allow_html=True)
    wc1,wc2 = st.columns(2)
    with wc1: inv_d = st.number_input("Inventory Days on Hand",0,365,45,help="F&B benchmark: 30–45 days")
    with wc2: dpo_d = st.number_input("Days Payable Outstanding (DPO)",0,180,30,help="Higher = better for working capital")
    st.markdown("</div>",unsafe_allow_html=True)

    if st.session_state.fc_df is not None and st.session_state.o2c_df is not None:
        _,cb,_ = st.columns([2,1,2])
        with cb:
            if st.button("🚀 Run Analysis",use_container_width=True):
                with st.spinner("Calculating metrics..."):
                    st.session_state.fc_m = calc_forecast(st.session_state.fc_df)
                    st.session_state.o2c_m = calc_o2c(st.session_state.o2c_df, industry)
                    st.session_state.wc_m = calc_wc(st.session_state.o2c_m, industry, inv_d, dpo_d)
                    st.session_state.mod_s = calc_modules(st.session_state.fc_m, st.session_state.o2c_m)
                with st.spinner("Running AI analysis..."):
                    try: st.session_state.ai = get_ai(st.session_state.fc_m, st.session_state.o2c_m, st.session_state.wc_m, region, industry)
                    except Exception as e: st.warning(f"AI error: {e}")
                st.session_state.done = True
                st.rerun()
        if st.session_state.done:
            st.success("✓ Analysis complete! Explore the tabs above.")

# ── TAB 2: DEMAND FORECASTING ─────────────────────────────────────────────────
with t2:
    st.markdown(f'<div style="font-size:1.3rem;font-weight:600;color:#0f172a">Demand Forecast Analysis</div><div style="font-size:0.9rem;color:#64748b;margin-bottom:1.5rem">Accuracy, MAPE, bias & SKU performance · {region} · {industry}</div>', unsafe_allow_html=True)
    if not st.session_state.done: st.info("Upload data and click Run Analysis.")
    else:
        fm = st.session_state.fc_m
        ac = fm["accuracy"]; ac_c = "#16a34a" if ac>=85 else "#ea580c" if ac>=70 else "#dc2626"
        bl = "Over-forecasting" if fm["bias"]>5 else "Under-forecasting" if fm["bias"]<-5 else "Well-calibrated"
        c1,c2,c3 = st.columns(3)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Forecast Accuracy</div><div class="metric-value" style="color:{ac_c}">{ac}%</div><div class="metric-delta {"good" if ac>=85 else "bad"}">{"✓ On target" if ac>=85 else "↓ Target: 85–90%"}</div>{tip("accuracy")}</div>',unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">MAPE</div><div class="metric-value">{fm["mape"]}%</div><div class="metric-delta {"good" if fm["mape"]<15 else "bad"}">{"✓ Within target" if fm["mape"]<15 else "↑ Above 15%"}</div>{tip("mape")}</div>',unsafe_allow_html=True)
        with c3:
            bc = "good" if abs(fm["bias"])<5 else "bad"
            st.markdown(f'<div class="metric-card"><div class="metric-label">Forecast Bias</div><div class="metric-value">{fm["bias"]:+.1f}%</div><div class="metric-delta {bc}">{bl}</div>{tip("bias")}</div>',unsafe_allow_html=True)
        st.markdown("<br>",unsafe_allow_html=True)
        cl,cr = st.columns(2)
        with cl:
            st.markdown('<div class="section-card"><div class="section-title">SKU Performance</div>',unsafe_allow_html=True)
            for _,row in fm["sku"].sort_values("Accuracy",ascending=False).iterrows():
                c = "#16a34a" if row["Accuracy"]>=85 else "#ea580c" if row["Accuracy"]>=70 else "#dc2626"
                st.markdown(f'<div style="margin-bottom:1rem"><div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:3px"><span style="font-weight:500">{row["SKU"]}</span><span style="color:{c};font-family:IBM Plex Mono,monospace;font-weight:500">{row["Accuracy"]}%</span></div><div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{min(100,row["Accuracy"])}%;background:{c}"></div></div><div style="font-size:0.75rem;color:#94a3b8;margin-top:3px">MAPE: {row["MAPE"]}% · Bias: {row["Bias"]:+.1f}%</div></div>',unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)
        with cr:
            st.markdown('<div class="section-card"><div class="section-title">Actual vs Forecast Trend</div>',unsafe_allow_html=True)
            monthly = fm["monthly"].groupby("Month").agg(Actual=("Actual_Units","sum"),Forecast=("Forecast_Units","sum")).reset_index()
            st.line_chart(monthly.set_index("Month")[["Actual","Forecast"]],color=["#0f172a","#94a3b8"])
            st.markdown("</div>",unsafe_allow_html=True)

# ── TAB 3: ORDER TO CASH ──────────────────────────────────────────────────────
with t3:
    st.markdown(f'<div style="font-size:1.3rem;font-weight:600;color:#0f172a">Order-to-Cash Performance</div><div style="font-size:0.9rem;color:#64748b;margin-bottom:1.5rem">DSO, invoice quality & payment delay risk · {region} · {industry}</div>', unsafe_allow_html=True)
    if not st.session_state.done: st.info("Upload data and click Run Analysis.")
    else:
        om = st.session_state.o2c_m
        dc = "#16a34a" if om["dso"]<=om["bench"] else "#ea580c" if om["dso"]<=om["bench"]*1.3 else "#dc2626"
        gs = "+" if om["gap"]>0 else ""
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Avg DSO</div><div class="metric-value" style="color:{dc}">{om["dso"]}d</div><div class="metric-delta {"bad" if om["gap"]>0 else "good"}">{gs}{om["gap"]}d vs {om["bench"]}d</div>{tip("dso")}</div>',unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Total Revenue</div><div class="metric-value" style="font-size:1.3rem">USD {om["rev"]:,.0f}</div><div class="metric-delta neutral">In analysis period</div></div>',unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Invoice Error Rate</div><div class="metric-value">{om["err"]}%</div><div class="metric-delta {"good" if om["err"]<2 else "bad"}">{"✓ Within range" if om["err"]<2 else "↑ Above 2%"}</div>{tip("error_rate")}</div>',unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">Dispute Rate</div><div class="metric-value">{om["disp"]}%</div><div class="metric-delta {"good" if om["disp"]<5 else "bad"}">{"✓ Acceptable" if om["disp"]<5 else "↑ Needs attention"}</div>{tip("dispute_rate")}</div>',unsafe_allow_html=True)
        st.markdown("<br>",unsafe_allow_html=True)
        cl,cr = st.columns(2)
        with cl:
            st.markdown('<div class="section-card"><div class="section-title">🚦 Payment Delay Risk — By Customer</div>',unsafe_allow_html=True)
            st.markdown('<div class="info-box">Traffic light shows payment risk based on each customer\'s DSO vs benchmark. Source: Kleen-Pak & Sime Darby — reactive collections is the #1 AR pain point.</div>',unsafe_allow_html=True)
            for _,row in om["cust"].iterrows():
                dc2 = "#dc2626" if "High" in row["Risk"] else "#f59e0b" if "Medium" in row["Risk"] else "#16a34a"
                pct = min(100,(row["Avg_DSO"]/120)*100)
                st.markdown(f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:1rem"><div style="width:14px;height:14px;border-radius:50%;background:{dc2};flex-shrink:0"></div><div style="flex:1"><div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:3px"><span style="font-weight:500">{row["Customer"]}</span><span style="font-family:IBM Plex Mono,monospace;font-weight:500;color:{dc2}">{row["Avg_DSO"]}d</span></div><div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{pct}%;background:{dc2}"></div></div><div style="font-size:0.72rem;color:#94a3b8;margin-top:2px">{row["Trend"]} · Benchmark: {om["bench"]}d</div></div></div>',unsafe_allow_html=True)
            st.markdown("<div style='font-size:0.78rem;color:#94a3b8'>🔴 High risk &nbsp; 🟡 Watch &nbsp; 🟢 On track</div></div>",unsafe_allow_html=True)
        with cr:
            st.markdown('<div class="section-card"><div class="section-title">DSO Distribution</div>',unsafe_allow_html=True)
            bk = pd.cut(st.session_state.o2c_df["DSO_Days"],bins=[0,30,45,60,90,999],labels=["<30d","30-45d","45-60d","60-90d",">90d"])
            st.bar_chart(bk.value_counts().sort_index())
            st.markdown(f"<div style='font-size:0.8rem;color:#64748b;margin-top:0.5rem'>{industry} benchmark: {om['bench']} days</div></div>",unsafe_allow_html=True)

# ── TAB 4: REVENUE LEAKAGE ────────────────────────────────────────────────────
with t4:
    st.markdown(f'<div style="font-size:1.3rem;font-weight:600;color:#0f172a">Revenue Leakage Analysis</div><div style="font-size:0.9rem;color:#64748b;margin-bottom:1.5rem">Where revenue is being lost across your O2C cycle · {region} · {industry}</div>', unsafe_allow_html=True)
    if not st.session_state.done: st.info("Upload data and click Run Analysis.")
    else:
        om = st.session_state.o2c_m
        rev = om["rev"]; net = rev - om["leak_total"]; lpct = round((om["leak_total"]/rev)*100,1)
        st.markdown('<div class="info-box">Revenue leakage is calculated from your actual error/dispute rates and SEA industry benchmarks for uncontrolled discounting and early payment deductions. Sources: Kleen-Pak CFO interview, Normality SPAN analysis Module 4.4.</div>',unsafe_allow_html=True)
        c1,c2,c3 = st.columns(3)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Gross Revenue</div><div class="metric-value" style="font-size:1.4rem">USD {rev:,.0f}</div><div class="metric-delta neutral">Total invoiced</div></div>',unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Estimated Leakage</div><div class="metric-value" style="color:#dc2626;font-size:1.4rem">USD {om["leak_total"]:,.0f}</div><div class="metric-delta bad">↓ {lpct}% of revenue</div>{tip("leakage")}</div>',unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Net Recovered Revenue</div><div class="metric-value" style="color:#16a34a;font-size:1.4rem">USD {net:,.0f}</div><div class="metric-delta good">After leakage adjustments</div></div>',unsafe_allow_html=True)
        st.markdown("<br>",unsafe_allow_html=True)
        cl,cr = st.columns([3,2])
        with cl:
            st.markdown('<div class="section-card"><div class="section-title">Revenue Leakage Waterfall</div>',unsafe_allow_html=True)
            bars = [
                ("Gross Revenue", rev, "#0f172a", "Starting point — total invoiced revenue"),
                ("Uncontrolled Discounting", -om["leak_disc"], "#dc2626", "Rogue discounting & below-threshold pricing. Source: Module 4.4, Shib interview"),
                ("Invoice Errors", -om["leak_inv"], "#ea580c", "Price/quantity errors & portal submission failures. Source: Kleen-Pak CFO"),
                ("Disputed Invoices", -om["leak_disp"], "#f59e0b", "Revenue delayed through customer disputes. Source: Module 4.2 — rebate & amendment mismatches"),
                ("Invalid Deductions", -om["leak_ded"], "#8b5cf6", "Early payment discounts taken outside contractual terms. Source: Kleen-Pak CFO"),
                ("Net Recovered Revenue", net, "#16a34a", "Revenue after all leakage types accounted for"),
            ]
            for label,value,color,desc in bars:
                neg = value < 0
                disp = f"-USD {abs(value):,.0f}" if neg else f"USD {value:,.0f}"
                pct = min(100,abs(value)/rev*100)
                st.markdown(f'<div style="margin-bottom:0.75rem"><div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:4px"><span style="font-weight:500">{label}</span><span style="font-family:IBM Plex Mono,monospace;font-weight:600;color:{color}">{disp}</span></div><div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{pct}%;background:{color}"></div></div><div style="font-size:0.72rem;color:#94a3b8;margin-top:3px">{desc}</div></div>',unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)
        with cr:
            st.markdown('<div class="section-card"><div class="section-title">Leakage Breakdown & Fixes</div>',unsafe_allow_html=True)
            items = [
                ("Uncontrolled Discounting",om["leak_disc"],"#dc2626","Fix: Discount governance layer with manager approval threshold"),
                ("Invoice Errors",om["leak_inv"],"#ea580c","Fix: Auto-invoice trigger + portal submission compliance bot"),
                ("Disputed Invoices",om["leak_disp"],"#f59e0b","Fix: Change-to-invoice propagation + rebate engine"),
                ("Invalid Deductions",om["leak_ded"],"#8b5cf6","Fix: Early payment discount validation module"),
            ]
            for label,val,color,fix in items:
                pct = round((val/max(om["leak_total"],1))*100,1)
                st.markdown(f'<div style="padding:0.75rem 0;border-bottom:1px solid #f1f5f9"><div style="display:flex;justify-content:space-between;margin-bottom:3px"><span style="font-size:0.85rem;font-weight:500;color:{color}">{label}</span><span style="font-size:0.85rem;font-family:IBM Plex Mono,monospace;font-weight:600">USD {val:,.0f}</span></div><div style="font-size:0.75rem;color:#94a3b8;margin-bottom:4px">{pct}% of total leakage</div><div style="font-size:0.78rem;color:#334155;background:#f8fafc;border-radius:6px;padding:4px 8px">{fix}</div></div>',unsafe_allow_html=True)
            st.markdown(f'<div style="margin-top:1rem;padding:0.75rem;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0"><div style="font-size:0.8rem;font-weight:600;color:#166534">💡 Total recoverable</div><div style="font-size:1.3rem;font-weight:600;color:#16a34a;font-family:IBM Plex Mono,monospace">USD {om["leak_total"]:,.0f}</div><div style="font-size:0.75rem;color:#166534;margin-top:2px">If all 4 leakage types are addressed</div></div>',unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)

# ── TAB 5: WORKING CAPITAL ────────────────────────────────────────────────────
with t5:
    st.markdown(f'<div style="font-size:1.3rem;font-weight:600;color:#0f172a">Working Capital Health</div><div style="font-size:0.9rem;color:#64748b;margin-bottom:1.5rem">Cash Conversion Cycle & O2C module health scores · {region} · {industry}</div>', unsafe_allow_html=True)
    if not st.session_state.done: st.info("Upload data and click Run Analysis.")
    else:
        wc = st.session_state.wc_m; ms = st.session_state.mod_s
        wcc = "#16a34a" if wc["score"]>=70 else "#ea580c" if wc["score"]>=45 else "#dc2626"
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">WC Health Score</div><div class="metric-value" style="color:{wcc}">{wc["score"]}</div><div class="metric-delta {"good" if wc["score"]>=70 else "bad"}">{wc["health"]}</div>{tip("ccc")}</div>',unsafe_allow_html=True)
        with c2:
            cc = "#16a34a" if wc["ccc"]<=wc["bench"] else "#dc2626"
            st.markdown(f'<div class="metric-card"><div class="metric-label">Cash Conversion Cycle</div><div class="metric-value" style="color:{cc}">{wc["ccc"]}d</div><div class="metric-delta {"bad" if wc["ccc"]>wc["bench"] else "good"}">Benchmark: {wc["bench"]}d</div></div>',unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">DSO Component</div><div class="metric-value">{wc["dso"]}d</div><div class="metric-delta neutral">Days to collect cash</div></div>',unsafe_allow_html=True)
        with c4:
            gc = "bad" if wc["gap"]>0 else "good"
            st.markdown(f'<div class="metric-card"><div class="metric-label">CCC Gap vs Benchmark</div><div class="metric-value" style="color:{"#dc2626" if wc["gap"]>0 else "#16a34a"}">{"+"+str(wc["gap"]) if wc["gap"]>0 else str(wc["gap"])}d</div><div class="metric-delta {gc}">{"Cash locked beyond benchmark" if wc["gap"]>0 else "Within benchmark"}</div></div>',unsafe_allow_html=True)
        st.markdown("<br>",unsafe_allow_html=True)
        st.markdown('<div class="section-card"><div class="section-title">Cash Conversion Cycle — DSO + Inventory Days − DPO</div>',unsafe_allow_html=True)
        st.markdown('<div class="info-box">Every day you reduce CCC unlocks working capital equal to Annual Revenue ÷ 365. Source: Sime Darby CIO — working capital visibility was a top CFO request.</div>',unsafe_allow_html=True)
        cc1,cc2,cc3 = st.columns(3)
        ccc_items = [("DSO (Days Sales Outstanding)",wc["dso"],"#dc2626","Reduce by: faster invoicing, portal compliance bot, AI dunning"),
                     ("Inventory Days",wc["inv"],"#f59e0b","Reduce by: dynamic safety stock, FEFO automation, better demand forecasting"),
                     ("DPO (Days Payable Outstanding)",wc["dpo"],"#16a34a","Increase by: renegotiating supplier payment terms")]
        for col,(label,val,color,fix) in zip([cc1,cc2,cc3],ccc_items):
            with col:
                st.markdown(f'<div class="metric-card" style="text-align:center"><div class="metric-label">{label}</div><div class="metric-value" style="color:{color}">{val}d</div><div style="font-size:0.78rem;color:#334155;margin-top:0.5rem;line-height:1.4">{fix}</div></div>',unsafe_allow_html=True)
        st.markdown("</div>",unsafe_allow_html=True)
        st.markdown("<br>",unsafe_allow_html=True)
        st.markdown('<div class="section-card"><div class="section-title">O2C Process Module Health — 5 Areas from Normality SPAN Analysis</div>',unsafe_allow_html=True)
        st.markdown('<div class="info-box">Scores derived from your data mapped against 25 sub-process pain points from the Normality SPAN project interviews and analysis.</div>',unsafe_allow_html=True)
        mc = st.columns(5)
        for col,(mname,mdata) in zip(mc,ms.items()):
            sc = mdata["score"]; mc2 = "#16a34a" if sc>=70 else "#ea580c" if sc>=45 else "#dc2626"
            with col:
                st.markdown(f'<div class="module-card"><div style="font-size:0.72rem;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;color:#64748b">{mname}</div><div style="font-size:2rem;font-weight:600;font-family:IBM Plex Mono,monospace;color:{mc2};margin:0.5rem 0 0.25rem">{sc}</div><div style="font-size:0.7rem;color:#94a3b8">out of 100</div><div style="font-size:0.8rem;color:#334155;margin-top:0.5rem;line-height:1.4">{mdata["pain"]}</div></div>',unsafe_allow_html=True)
        st.markdown("</div>",unsafe_allow_html=True)

# ── TAB 6: MARKET INTEL + AI ──────────────────────────────────────────────────
with t6:
    st.markdown(f'<div style="font-size:1.3rem;font-weight:600;color:#0f172a">Market Intelligence & AI Insights</div><div style="font-size:0.9rem;color:#64748b;margin-bottom:1.5rem">Live market signals + AI recommendations · {region} · {industry}</div>', unsafe_allow_html=True)

    if st.session_state.done and st.session_state.ai:
        ai = st.session_state.ai
        sc = ai.get("health_score",0); hl = ai.get("overall_health","Unknown")
        hc = "#16a34a" if sc>=70 else "#ea580c" if sc>=50 else "#dc2626"
        cs,csm = st.columns([1,2])
        with cs:
            st.markdown(f'<div class="metric-card" style="text-align:center;padding:2rem 1.5rem"><div class="metric-label">Overall Health Score</div><div class="metric-value" style="color:{hc};font-size:3.5rem">{sc}</div><div style="font-size:0.9rem;font-weight:600;color:{hc};margin-top:0.5rem">{hl}</div><div style="font-size:0.78rem;color:#94a3b8;margin-top:0.4rem">{region} · {industry}</div></div>',unsafe_allow_html=True)
        with csm:
            st.markdown('<div class="section-card"><div class="section-title">Executive Summary</div>',unsafe_allow_html=True)
            st.markdown(f"<p style='color:#334155;line-height:1.7;font-size:0.95rem'>{ai.get('executive_summary','')}</p></div>",unsafe_allow_html=True)
        st.markdown("<br>",unsafe_allow_html=True)
        cl,cr = st.columns(2)
        with cl:
            st.markdown('<div class="section-card"><div class="section-title">Top Risks by Module</div>',unsafe_allow_html=True)
            for r in ai.get("top_risks",[]):
                sev=r.get("severity","Medium"); bc="risk-high" if sev=="High" else "risk-med" if sev=="Medium" else "risk-low"
                st.markdown(f'<div class="insight-row"><div><span class="risk-badge {bc}">{sev}</span><span style="font-size:0.72rem;background:#f1f5f9;padding:2px 8px;border-radius:20px;margin-left:6px;color:#64748b">{r.get("module","")}</span><div style="font-weight:500;margin-top:0.4rem;font-size:0.9rem">{r.get("risk","")}</div><div style="font-size:0.82rem;color:#64748b;margin-top:0.25rem">{r.get("impact","")}</div></div></div>',unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)
            if ai.get("wc_insight"):
                st.markdown("<br>",unsafe_allow_html=True)
                st.markdown(f'<div class="section-card"><div class="section-title">Working Capital Intelligence</div><p style="color:#334155;line-height:1.7;font-size:0.9rem">{ai.get("wc_insight","")}</p></div>',unsafe_allow_html=True)
        with cr:
            st.markdown('<div class="section-card"><div class="section-title">Quick Wins — Sourced from Interviews & Analysis</div>',unsafe_allow_html=True)
            for i,qw in enumerate(ai.get("quick_wins",[]),1):
                src=qw.get("source",""); sc2="#0369a1" if src=="Interview" else "#166534" if src=="Excel" else "#64748b"
                st.markdown(f'<div class="insight-row"><div style="background:#f1f5f9;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:0.75rem;font-weight:600;color:#0f172a;flex-shrink:0;margin-top:2px">{i}</div><div><div style="font-weight:500;font-size:0.9rem">{qw.get("action","")}</div><div style="font-size:0.8rem;color:#64748b;margin-top:0.25rem">⏱ {qw.get("timeline","")} · 📈 {qw.get("expected_impact","")}</div><span style="font-size:0.7rem;background:#f0f9ff;color:{sc2};padding:2px 8px;border-radius:20px;margin-top:4px;display:inline-block">Source: {src}</span></div></div>',unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)
            if ai.get("forecast_insight"):
                st.markdown("<br>",unsafe_allow_html=True)
                st.markdown(f'<div class="section-card"><div class="section-title">Forecast Intelligence</div><p style="color:#334155;line-height:1.7;font-size:0.9rem">{ai.get("forecast_insight","")}</p></div>',unsafe_allow_html=True)
    elif not st.session_state.done:
        st.info("Run analysis first to see AI insights.")

    st.markdown("---")
    st.markdown("### 🌐 Live Market Intelligence")
    cb2,cn2 = st.columns([1,3])
    with cb2:
        fetch = st.button("🔍 Fetch Market Data",use_container_width=True)
    with cn2:
        st.markdown('<div class="info-box"><strong>Hard data only.</strong> RSS feeds · World Bank API · Google Trends. Gemini interprets numbers — never invents.</div>',unsafe_allow_html=True)

    if fetch:
        with st.spinner("Fetching news..."): st.session_state.tnews = fetch_news(region, industry)
        with st.spinner("Fetching World Bank data..."): st.session_state.twb = fetch_wb(region, industry)
        with st.spinner("Fetching Google Trends..."): st.session_state.tgt = fetch_gt(INDUSTRIES[industry]["keywords"][:3], region)
        with st.spinner("AI interpreting real data..."):
            try: st.session_state.tai = get_trend_ai(region, industry, st.session_state.tnews or [], st.session_state.twb or {}, st.session_state.tgt or {})
            except Exception as e: st.session_state.tai = f"Error: {e}"
        st.session_state.tfetched = True; st.rerun()

    if not st.session_state.tfetched:
        st.markdown('<div class="upload-hint">Click "Fetch Market Data" to pull live signals.</div>',unsafe_allow_html=True)
    else:
        if st.session_state.tai:
            st.markdown(f'<div class="section-card"><div class="section-title">🧠 AI Market Summary — Real Data Only</div><div style="color:#334155;line-height:1.75;font-size:0.95rem">{st.session_state.tai.replace(chr(10),"<br>")}</div></div>',unsafe_allow_html=True)
        cl2,cr2 = st.columns(2)
        with cl2:
            st.markdown('<div class="section-card"><div class="section-title">📰 RSS News Feeds</div>',unsafe_allow_html=True)
            if st.session_state.tnews:
                for a in st.session_state.tnews[:8]:
                    tags="".join([f'<span class="news-tag">{k}</span>' for k in a["keywords"]])
                    st.markdown(f'<div class="news-card"><div style="font-size:0.9rem;font-weight:500;color:#0f172a;margin-bottom:0.25rem">{a["title"]}</div><div style="font-size:0.75rem;color:#94a3b8">{a["source"]} · {a["published"]}</div><div style="margin-top:0.4rem">{tags}</div></div>',unsafe_allow_html=True)
            else: st.markdown("<div style='color:#94a3b8;font-size:0.9rem'>No matching articles found.</div>",unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)
        with cr2:
            st.markdown('<div class="section-card"><div class="section-title">🌍 World Bank Indicators</div>',unsafe_allow_html=True)
            if st.session_state.twb:
                for label,series in st.session_state.twb.items():
                    if series:
                        latest=series[-1]
                        st.markdown(f"**{label}** — Latest: `{latest['value']}` ({latest['year']})")
                        st.line_chart(pd.DataFrame(series).set_index("year")["value"])
            else: st.markdown("<div style='color:#94a3b8'>World Bank data unavailable.</div>",unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)
            st.markdown('<div class="section-card"><div class="section-title">📈 Google Trends — Last 30 Days</div>',unsafe_allow_html=True)
            gt = st.session_state.tgt
            if gt and gt.get("data"):
                for kw,series in gt["data"].items():
                    st.markdown(f"**{kw}**")
                    st.line_chart(pd.DataFrame(series).set_index("date")["value"])
            elif gt and gt.get("error"):
                st.markdown(f'<div class="warn-box"><strong>Note:</strong> {gt["error"]}</div>',unsafe_allow_html=True)
            st.markdown("</div>",unsafe_allow_html=True)
