"""Shared app state: demand history + trained forecaster (retrains automatically when the log changes)."""
import os
import pandas as pd
import streamlit as st
import config as C
from adapters.synthetic import save_default, generate_demand
from services.forecaster import Forecaster, load_demand, add_actual
from services.recipes import load_catalog

@st.cache_resource(show_spinner="Training the forecaster...")
def _fit(_df, key):
    return Forecaster.fit(_df)

@st.cache_resource
def catalog():
    return load_catalog()

def _key(df):
    return int(pd.util.hash_pandas_object(df, index=False).sum() % (2 ** 61))

def demand_df():
    if "demand_df" not in st.session_state:
        if not os.path.exists(C.DEMAND_LOG):
            save_default(C.DEMAND_LOG)
        st.session_state["demand_df"] = load_demand(C.DEMAND_LOG)
        st.session_state["demand_source"] = "demo (synthetic) file"
    return st.session_state["demand_df"]

def model():
    df = demand_df()
    return _fit(df, _key(df))

def set_demand(df, source, persist=False):
    st.session_state["demand_df"] = df
    st.session_state["demand_source"] = source
    if persist:
        os.makedirs(os.path.dirname(C.DEMAND_LOG) or ".", exist_ok=True)
        df.drop(columns=[c for c in df.columns if c.startswith("lag")], errors="ignore").to_csv(C.DEMAND_LOG, index=False)

def log_actual(d, meal, consumed, prepared, flags):
    new = add_actual(demand_df(), d, meal, consumed, prepared, flags)
    set_demand(new, st.session_state["demand_source"], persist=st.session_state["demand_source"].startswith("demo"))

def regenerate(strength):
    set_demand(generate_demand(strength=strength), "demo (synthetic) file", persist=True)
