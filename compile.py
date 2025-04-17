import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
from google.oauth2.service_account import Credentials
from st_aggrid import AgGrid, GridOptionsBuilder
import json
from datetime import datetime

# Configuration
@st.cache_resource
def load_credentials():
    """Load Google Sheets credentials with caching"""
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", 
              "https://www.googleapis.com/auth/drive"]
    try:
        # Try Streamlit Secrets (for cloud)
        service_account_info = json.loads(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    except:
        # Fallback to local file (for development)
        try:
            creds = Credentials.from_service_account_file("service-account.json", scopes=SCOPES)
        except Exception as e:
            st.error(f"Failed to load Google credentials: {str(e)}")
            st.stop()
    return gspread.authorize(creds)

gc = load_credentials()

# Constants
COLOR_MAP = {
    'Present': '#7B68EE',  # mediumpurple
    'Absent': '#FFEFD5',   # papayawhip
    'Payable': '#7B68EE',
    'Absent': '#FFEFD5',
    'Yes': '#7B68EE',
    'No': '#FFEFD5',
    'Defaulter': '#FF6B6B',
    'Non-Defaulter': '#66BB6A'
}

# Data Loading with Caching and Validation
@st.cache_data(ttl=3600)
def load_sheet_data(_gc, sheet_key, worksheet_name):
    """Load and validate worksheet data"""
    try:
        spreadsheet = _gc.open_by_key(sheet_key)
        worksheet = spreadsheet.worksheet(worksheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Basic validation
        if df.empty:
            st.warning(f"Empty dataframe loaded from {worksheet_name}")
            return df
            
        # Clean column names
        df.columns = [col.strip() for col in df.columns]
        
        return df
    except Exception as e:
        st.error(f"Error loading {worksheet_name}: {str(e)}")
        return pd.DataFrame()

# Load main datasets
MAIN_SHEET_KEY = "1DEsQQMwkcGaHIUpirSLoFsM0HSSq1nlYB9PynDW-txQ"
DAILY_SHEET_KEY = "1J2XQPhOc2OqDcjjg_9-WLA7RbtveaLI5ddK91I6cwlw"

df = load_sheet_data(gc, MAIN_SHEET_KEY, "Main")
df_monthly = load_sheet_data(gc, MAIN_SHEET_KEY, "pdftosheet")

# Data Cleaning Functions
def clean_main_data(df):
    """Clean and process main dataframe"""
    if df.empty:
        return df
    
    # Convert numeric columns
    numeric_cols = ['SUM of Payable Days', 'Updated Absent Days', 'Extension Days', 'Year']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Clean text columns
    text_cols = ['Name', 'Transfer case']
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df = df[df[col] != 'nan']
    
    
def clean_monthly_data(df):
    """Clean and process monthly dataframe"""
    if df.empty:
        return df
    
    # Convert numeric columns
    numeric_cols = ['Payable Days', 'Absent Days', 'Days in Month', 'Salary']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Clean text columns
    if 'Name' in df.columns:
        df['Name'] = df['Name'].astype(str).str.strip()
        df = df[df['Name'] != 'nan']
    
    # Clean Month column
    if 'Month' in df.columns:
        df['Month'] = df['Month'].astype(str).str.strip()
    
    return df

# Apply cleaning
df = clean_main_data(df)
df_monthly = clean_monthly_data(df_monthly)

# Helper Functions
def safe_plot(plot_func, *args, **kwargs):
    """Wrapper for plotly express functions with error handling"""
    try:
        fig = plot_func(*args, **kwargs)
        fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#2c3e50')
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error generating plot: {str(e)}")
        if 'data_frame' in kwargs:
            st.write("Data sample:", kwargs['data_frame'].head())
        st.write("Arguments:", args)
        st.write("Keyword arguments:", kwargs)

def format_currency(amount):
    """Format numbers as currency"""
    try:
        return f"₹{amount:,.0f}"
    except:
        return str(amount)

# Streamlit App Configuration
st.set_page_config(
    page_title="DRC Attendance Dashboard",
    layout="wide",
    page_icon="📊"
)

# Sidebar Navigation
st.sidebar.title("Navigation")
page_selection = st.sidebar.radio("Go to", ["Main Dashboard", "Monthly Data", "Individual Dashboard", "Daily Dashboard"])

# Main Dashboard Page
if page_selection == "Main Dashboard":
    st.title("DRC Attendance Dashboard")
    
    # Sidebar Filters
    st.sidebar.title("Filter Options")
    article_list = ["All"] + sorted(df['Name'].unique().tolist())
    selected_article = st.sidebar.selectbox("Select Article Name", article_list)
    
    # Filter data
    if selected_article == "All":
        filtered_df = df
    else:
        filtered_df = df[df['Name'] == selected_article]
    
    # KPIs
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)
        with col1:
            present_days = filtered_df['SUM of Payable Days'].sum()
            st.metric("Total Present Days", present_days)
        
        with col2:
            absent_days = filtered_df['Updated Absent Days'].sum()
            st.metric("Total Absent Days", absent_days)
        
        with col3:
            defaulter_count = filtered_df[filtered_df['Defaulter'] == 'Defaulter'].shape[0]
            st.metric("Defaulters", defaulter_count)
    
    # Visualizations
    if not filtered_df.empty:
        # Present vs Absent Days
        st.subheader("Present vs Absent Days by Article")
        present_absent = filtered_df.groupby('Name').agg({
            'SUM of Payable Days': 'sum',
            'Updated Absent Days': 'sum'
        }).reset_index()
        
        safe_plot(
            px.bar,
            data_frame=present_absent.melt(id_vars='Name', var_name='Type', value_name='Days'),
            x='Name',
            y='Days',
            color='Type',
            barmode='group',
            color_discrete_map={
                'SUM of Payable Days': COLOR_MAP['Present'],
                'Updated Absent Days': COLOR_MAP['Absent']
            },
            labels={'Name': 'Article', 'Days': 'Number of Days'},
            height=500
        )
        
        # Defaulter Visualization
        st.subheader("Defaulter Status")
        safe_plot(
            px.bar,
            data_frame=filtered_df,
            x='Name',
            y='Updated Absent Days',
            color='Defaulter',
            color_discrete_map=COLOR_MAP,
            labels={'Name': 'Article', 'Updated Absent Days': 'Days Absent'},
            height=500
        )
        
        # Transfer Case and Extension Days
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Transfer Case Distribution")
            transfer_counts = filtered_df['Transfer case'].value_counts().reset_index()
            transfer_counts.columns = ['Transfer case', 'Count']
            
            safe_plot(
                px.pie,
                data_frame=transfer_counts,
                names='Transfer case',
                values='Count',
                color_discrete_map=COLOR_MAP,
                hole=0.4
            )
        
        with col2:
            st.subheader("Extension Days")
            extension_df = filtered_df[filtered_df['Extension Days'] > 0]
            if not extension_df.empty:
                safe_plot(
                    px.bar,
                    data_frame=extension_df.sort_values('Extension Days', ascending=False),
                    x='Name',
                    y='Extension Days',
                    color_discrete_sequence=[COLOR_MAP['Present']],
                    labels={'Name': 'Article', 'Extension Days': 'Days'},
                    height=400
                )
            else:
                st.info("No extension days recorded")
    
    

# Monthly Data Page
elif page_selection == "Monthly Data":
    st.title("Monthly Attendance Data")
    
    # Sidebar Filters
    st.sidebar.title("Filter Options")
    month_list = ["All"] + sorted(df_monthly['Month'].unique().tolist())
    selected_month = st.sidebar.selectbox("Select Month", month_list)
    
    # Filter data
    if selected_month == "All":
        filtered_monthly = df_monthly
    else:
        filtered_monthly = df_monthly[df_monthly['Month'] == selected_month]
    
    # KPIs
    if not filtered_monthly.empty:
        col1, col2, col3 = st.columns(3)
        with col1:
            total_salary = filtered_monthly['Salary'].sum()
            st.metric("Total Salary", format_currency(total_salary))
        
        with col2:
            payable_days = filtered_monthly['Payable Days'].sum()
            st.metric("Total Payable Days", payable_days)
        
        with col3:
            absent_days = filtered_monthly['Absent Days'].sum()
            st.metric("Total Absent Days", absent_days)
    
    # Visualizations
    if not filtered_monthly.empty:
        # Salary Distribution
        st.subheader("Salary Distribution")
        safe_plot(
            px.bar,
            data_frame=filtered_monthly,
            x='Name',
            y='Salary',
            color='Name',
            labels={'Salary': 'Amount (₹)', 'Name': 'Article'},
            height=500
        )
        
        # Present vs Absent Days
        st.subheader("Attendance Days")
        safe_plot(
            px.bar,
            data_frame=filtered_monthly.melt(
                id_vars=['Name', 'Month'],
                value_vars=['Payable Days', 'Absent Days'],
                var_name='Type',
                value_name='Days'
            ),
            x='Name',
            y='Days',
            color='Type',
            barmode='group',
            color_discrete_map={
                'Payable Days': COLOR_MAP['Present'],
                'Absent Days': COLOR_MAP['Absent']
            },
            labels={'Name': 'Article', 'Days': 'Number of Days'},
            height=500
        )
        
        # Salary Trend Over Time
        if selected_month == "All":
            st.subheader("Salary Trend Over Months")
            salary_trend = df_monthly.groupby(['Month', 'Name'])['Salary'].sum().reset_index()
            safe_plot(
                px.line,
                data_frame=salary_trend,
                x='Month',
                y='Salary',
                color='Name',
                markers=True,
                labels={'Salary': 'Amount (₹)', 'Month': 'Month'},
                height=500
            )
    
    

# Individual Dashboard Page
elif page_selection == "Individual Dashboard":
    st.title("Individual Article Dashboard")
    
    # Sidebar Filters
    st.sidebar.title("Filter Options")
    article_list = ["All"] + sorted(df['Name'].unique().tolist())
    selected_article = st.sidebar.selectbox("Select Article Name", article_list)
    
    month_list = ["All"] + sorted(df_monthly['Month'].unique().tolist())
    selected_month = st.sidebar.selectbox("Select Month", month_list)
    
    # Filter data
    if selected_article == "All":
        filtered_df = df
        filtered_monthly = df_monthly
    else:
        filtered_df = df[df['Name'] == selected_article]
        filtered_monthly = df_monthly[df_monthly['Name'] == selected_article]
    
    if selected_month != "All":
        filtered_monthly = filtered_monthly[filtered_monthly['Month'] == selected_month]
    
    # Display KPIs
    if not filtered_df.empty and selected_article != "All":
        st.subheader(f"Performance Overview for {selected_article}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            total_present = filtered_df['SUM of Payable Days'].sum()
            st.metric("Total Present Days", total_present)
        
        with col2:
            total_absent = filtered_df['Updated Absent Days'].sum()
            st.metric("Total Absent Days", total_absent)
        
        with col3:
            defaulter_status = filtered_df['Defaulter'].iloc[0] if not filtered_df.empty else 'Unknown'
            st.metric("Defaulter Status", defaulter_status)
    
    # Visualizations
    if not filtered_monthly.empty:
        # Attendance Breakdown
        st.subheader("Attendance Breakdown")
        
        if selected_month == "All":
            # Show trend over months
            safe_plot(
                px.line,
                data_frame=filtered_monthly,
                x='Month',
                y=['Payable Days', 'Absent Days'],
                markers=True,
                color_discrete_map={
                    'Payable Days': COLOR_MAP['Present'],
                    'Absent Days': COLOR_MAP['Absent']
                },
                labels={'value': 'Days', 'variable': 'Type'},
                height=400
            )
        else:
            # Show pie chart for single month
            pie_data = {
                'Category': ['Payable Days', 'Absent Days', 'Other Days'],
                'Count': [
                    filtered_monthly['Payable Days'].sum(),
                    filtered_monthly['Absent Days'].sum(),
                    filtered_monthly['Days in Month'].sum() - 
                    (filtered_monthly['Payable Days'].sum() + 
                     filtered_monthly['Absent Days'].sum())
                ]
            }
            pie_df = pd.DataFrame(pie_data)
            pie_df['Count'] = pie_df['Count'].clip(lower=0)
            
            safe_plot(
                px.pie,
                data_frame=pie_df,
                names='Category',
                values='Count',
                color='Category',
                color_discrete_map={
                    'Payable Days': COLOR_MAP['Present'],
                    'Absent Days': COLOR_MAP['Absent'],
                    'Other Days': '#CCCCCC'
                },
                height=400
            )
        
        # Salary Information
        if 'Salary' in filtered_monthly.columns:
            st.subheader("Salary Information")
            safe_plot(
                px.bar,
                data_frame=filtered_monthly,
                x='Month' if selected_month == "All" else 'Name',
                y='Salary',
                labels={'Salary': 'Amount (₹)'},
                height=400
            )
    
    # Data Tables
    if not filtered_df.empty:
        st.subheader("Annual Data")
        AgGrid(
            filtered_df,
            height=200,
            theme='streamlit',
            enable_enterprise_modules=True
        )
    
    if not filtered_monthly.empty:
        st.subheader("Monthly Data")
        AgGrid(
            filtered_monthly,
            height=300,
            theme='streamlit',
            enable_enterprise_modules=True
        )

# Daily Dashboard Page
elif page_selection == "Daily Dashboard":
    st.title("Daily Attendance Dashboard")
    
    # Load daily data
    daily_spreadsheet = gc.open_by_key(DAILY_SHEET_KEY)
    worksheets = [ws for ws in daily_spreadsheet.worksheets() if ws.title != "Sheet1"]
    available_sheets = [ws.title for ws in worksheets]
    
    # Sidebar Filters
    st.sidebar.title("Daily Data Filters")
    selected_sheet = st.sidebar.selectbox("Select Month Sheet", available_sheets)
    
    # Load selected worksheet
    @st.cache_data(ttl=600)
    def load_daily_data(_gc, sheet_key, sheet_name):
        try:
            spreadsheet = _gc.open_by_key(sheet_key)
            worksheet = spreadsheet.worksheet(sheet_name)
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Error loading daily data: {str(e)}")
            return pd.DataFrame()

    daily_df = load_daily_data(gc, DAILY_SHEET_KEY, selected_sheet)
    
    # Process daily data
    if not daily_df.empty:
        # Convert and clean date column
        if 'Date' in daily_df.columns:
            daily_df['Date'] = pd.to_datetime(daily_df['Date'], errors='coerce', dayfirst=True)
            daily_df = daily_df.dropna(subset=['Date'])
            
            # Date range filter
            min_date = daily_df['Date'].min().to_pydatetime()
            max_date = daily_df['Date'].max().to_pydatetime()
            
            date_range = st.sidebar.date_input(
                "Select Date Range",
                value=[min_date, max_date],
                min_value=min_date,
                max_value=max_date
            )
            
            if len(date_range) == 2:
                start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
                daily_df = daily_df[(daily_df['Date'] >= start_date) & (daily_df['Date'] <= end_date)]
        
        # Staff name filter
        staff_names = ["All"] + sorted(daily_df['Staff Name'].unique().tolist())
        selected_staff = st.sidebar.selectbox("Select Staff Member", staff_names)
        
        if selected_staff != "All":
            daily_df = daily_df[daily_df['Staff Name'] == selected_staff]
        
        # Process Hours Worked
        if 'Hours Worked' in daily_df.columns:
            daily_df['Hours Worked'] = daily_df['Hours Worked'].apply(
                lambda x: float(x) if isinstance(x, (int, float)) else 0.0
            )
    
    # Display KPIs
    if not daily_df.empty:
        st.subheader("Daily Summary")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            total_days = daily_df.shape[0]
            st.metric("Total Days Recorded", total_days)
        
        with col2:
            if 'Hours Worked' in daily_df.columns:
                avg_hours = daily_df['Hours Worked'].mean()
                st.metric("Average Hours Worked", f"{avg_hours:.1f} hours")
        
        with col3:
            if 'Attendance' in daily_df.columns:
                present_count = daily_df[daily_df['Attendance'] == 'Present'].shape[0]
                st.metric("Days Present", f"{present_count}/{total_days}")
    
    # Visualizations
    if not daily_df.empty:
        # Attendance Status
        if 'Attendance' in daily_df.columns:
            st.subheader("Attendance Status")
            status_counts = daily_df['Attendance'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            
            safe_plot(
                px.pie,
                data_frame=status_counts,
                names='Status',
                values='Count',
                color_discrete_sequence=px.colors.qualitative.Pastel,
                height=400
            )
        
        # Hours Worked Trend
        if 'Hours Worked' in daily_df.columns and 'Date' in daily_df.columns:
            st.subheader("Hours Worked Trend")
            safe_plot(
                px.line,
                data_frame=daily_df.sort_values('Date'),
                x='Date',
                y='Hours Worked',
                color=None if selected_staff != "All" else 'Staff Name',
                labels={'Hours Worked': 'Hours', 'Date': 'Date'},
                height=400
            )
    
    # Data Table
    if not daily_df.empty:
        st.subheader("Daily Records")
        AgGrid(
            daily_df,
            height=500,
            theme='streamlit',
            enable_enterprise_modules=True,
            fit_columns_on_grid_load=True
        )
    else:
        st.warning("No daily data available for selected filters")

# Add some debug info in sidebar
st.sidebar.title("Debug Info")
if st.sidebar.checkbox("Show Data Info"):
    st.sidebar.write("Main DF Shape:", df.shape)
    st.sidebar.write("Monthly DF Shape:", df_monthly.shape)
    if page_selection == "Daily Dashboard":
        st.sidebar.write("Daily DF Shape:", daily_df.shape if 'daily_df' in locals() else 0)