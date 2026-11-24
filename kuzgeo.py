import math
import io
import streamlit as st
import folium
import streamlit.components.v1 as components
from fpdf import FPDF

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Zambian Cadastral Computation Tool",
    page_icon="📐",
    layout="wide"
)

st.title("📐 Zambian Cadastral Survey Computation Engine")
st.caption("GE500 Topic 1.4: Bearings, Distances &amp; Official Report Generation")

# --- MATHEMATICAL ENGINE (JOIN COMPUTATION) ---
def calculate_join(e1, n1, e2, n2):
    """Computes Delta Easting, Delta Northing, Distance, and WCB in DMS."""
    de = e2 - e1
    dn = n2 - n1
    dist = math.hypot(de, dn)
    
    # Whole Circle Bearing (0° to 360°)
    rad = math.atan2(de, dn)
    deg_raw = math.degrees(rad)
    wcb_deg = (deg_raw + 360) % 360
    
    # Convert WCB to Degrees, Minutes, Seconds (DMS)
    d = int(wcb_deg)
    m_full = (wcb_deg - d) * 60
    m = int(m_full)
    s = round((m_full - m) * 60, 1)
    if s >= 60.0:
        s = 0.0
        m += 1
    if m >= 60:
        m = 0
        d = (d + 1) % 360
        
    dms_str = f"{d}° {m:02d}' {s:04.1f}\""
    return de, dn, dist, wcb_deg, dms_str

# --- PDF REPORT GENERATOR ---
def generate_pdf(stn_a, e1, n1, stn_b, e2, n2, de, dn, dist, wcb_dms):
    class PDFReport(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 14)
            self.cell(0, 8, 'ZAMBIAN CADASTRAL SURVEY COMPUTATION SHEET', new_x='LMARGIN', new_y='NEXT', align='C')
            self.set_font('Helvetica', 'I', 10)
            self.cell(0, 5, 'GE500 Topic 1.4: Cadastral Survey Web Engine', new_x='LMARGIN', new_y='NEXT', align='C')
            self.line(10, 25, 200, 25)
            self.ln(8)
            
        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', align='C')

    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, '1. Station Coordinates (National Grid / Local Coordinates)', new_x='LMARGIN', new_y='NEXT')
    
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(95, 7, f'Station A ({stn_a}): E = {e1:,.3f} m | N = {n1:,.3f} m', border=1)
    pdf.cell(95, 7, f'Station B ({stn_b}): E = {e2:,.3f} m | N = {n2:,.3f} m', border=1, new_x='LMARGIN', new_y='NEXT')
    
    pdf.ln(5)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, '2. Computed Join Results', new_x='LMARGIN', new_y='NEXT')
    
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(60, 7, 'Parameter', border=1)
    pdf.cell(130, 7, 'Computed Value', border=1, new_x='LMARGIN', new_y='NEXT')
    
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(60, 7, 'Delta Easting (dE)', border=1)
    pdf.cell(130, 7, f'{de:+,.3f} m', border=1, new_x='LMARGIN', new_y='NEXT')
    
    pdf.cell(60, 7, 'Delta Northing (dN)', border=1)
    pdf.cell(130, 7, f'{dn:+,.3f} m', border=1, new_x='LMARGIN', new_y='NEXT')
    
    pdf.cell(60, 7, 'Horizontal Distance (d)', border=1)
    pdf.cell(130, 7, f'{dist:,.3f} m', border=1, new_x='LMARGIN', new_y='NEXT')
    
    pdf.cell(60, 7, 'Whole Circle Bearing (WCB)', border=1)
    pdf.cell(130, 7, f'{wcb_dms}', border=1, new_x='LMARGIN', new_y='NEXT')
    
    return bytes(pdf.output())

# --- USER INTERFACE LAYOUT ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Enter Station Data")
    stn_a = st.text_input("Station A Name", value="STN_1")
    e1 = st.number_input("Station A Easting (m)", value=1000.000, step=0.001, format="%.3f")
    n1 = st.number_input("Station A Northing (m)", value=2000.000, step=0.001, format="%.3f")
    
    st.markdown("---")
    stn_b = st.text_input("Station B Name", value="STN_2")
    e2 = st.number_input("Station B Easting (m)", value=1250.000, step=0.001, format="%.3f")
    n2 = st.number_input("Station B Northing (m)", value=2450.000, step=0.001, format="%.3f")

# --- CALCULATIONS &amp; OUTPUT ---
de, dn, dist, wcb_deg, dms_str = calculate_join(e1, n1, e2, n2)

with col2:
    st.subheader("2. Calculation Results")
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("Horizontal Distance", f"{dist:,.3f} m")
    m_col2.metric("Bearing (WCB)", dms_str)
    
    st.write(f"**Delta Easting (ΔE):** `{de:+,.3f} m`")
    st.write(f"**Delta Northing (ΔN):** `{dn:+,.3f} m`")
    
    st.markdown("---")
    st.subheader("3. PDF Computation Sheet")
    pdf_data = generate_pdf(stn_a, e1, n1, stn_b, e2, n2, de, dn, dist, dms_str)
    
    st.download_button(
        label="📄 Download Official PDF Report",
        data=pdf_data,
        file_name=f"Join_{stn_a}_{stn_b}.pdf",
        mime="application/pdf"
    )

st.markdown("---")
st.subheader("4. Interactive Map Preview")

# Approximate Map Center (for local coordinates or reference plotting)
# Converts relative cartesian offsets to sample map location for demonstration
base_lat, base_lon = -12.8000, 28.2000 
lat_a, lon_a = base_lat, base_lon
lat_b = base_lat + (dn / 111000.0)
lon_b = base_lon + (de / 108000.0)

m = folium.Map(location=[(lat_a + lat_b)/2, (lon_a + lon_b)/2], zoom_start=15)
folium.Marker([lat_a, lon_a], popup=f"{stn_a}", icon=folium.Icon(color="red")).add_to(m)
folium.Marker([lat_b, lon_b], popup=f"{stn_b}", icon=folium.Icon(color="blue")).add_to(m)
folium.PolyLine([[lat_a, lon_a], [lat_b, lon_b]], color="green", weight=4, opacity=0.8).add_to(m)

# Render Folium Map in Streamlit
components.html(m._repr_html_(), height=450)
