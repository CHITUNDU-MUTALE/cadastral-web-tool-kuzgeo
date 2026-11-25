import math
import io
import streamlit as st
import folium
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
from fpdf import FPDF

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Zambian Cadastral Survey Computation Engine",
    layout="wide"
)

st.title("Zambian Cadastral Survey Computation Engine")
st.caption("GE500 Topic 1.4: Bearings, Distances, Bowditch Adjustment, Area & 2D Helmert Transformation")

# --- MATHEMATICAL HELPER FUNCTIONS ---

def dms_to_deg(d, m, s):
    """Converts Degrees, Minutes, Seconds to Decimal Degrees."""
    sign = -1 if d < 0 else 1
    return sign * (abs(d) + m / 60.0 + s / 3600.0)

def deg_to_dms(deg):
    """Converts Decimal Degrees to Degrees, Minutes, Seconds string."""
    deg_norm = (deg + 360) % 360
    d = int(deg_norm)
    m_full = (deg_norm - d) * 60
    m = int(m_full)
    s = round((m_full - m) * 60, 1)
    if s >= 60.0:
        s = 0.0
        m += 1
    if m >= 60:
        m = 0
        d = (d + 1) % 360
    return f"{d}° {m:02d}' {s:04.1f}\""

def calculate_join(e1, n1, e2, n2):
    """Computes Join between two points: dE, dN, Distance, WCB."""
    de = e2 - e1
    dn = n2 - n1
    dist = math.hypot(de, dn)
    rad = math.atan2(de, dn)
    wcb = (math.degrees(rad) + 360) % 360
    return de, dn, dist, wcb, deg_to_dms(wcb)

def calculate_shoelace_area(coords):
    """Computes polygon area using Gauss Shoelace Formula."""
    n = len(coords)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += coords[i][0] * coords[j][1]
        area -= coords[j][0] * coords[i][1]
    return abs(area) / 2.0

def bowditch_traverse_adjustment(df_traverse, start_e, start_n):
    """
    Performs Bowditch adjustment given leg distances and bearings.
    df_traverse columns: ['Leg', 'Distance_m', 'WCB_deg']
    """
    records = []
    total_dist = df_traverse['Distance_m'].sum()
    
    # 1. Compute raw departures (dE) and latitudes (dN)
    raw_de = []
    raw_dn = []
    for _, row in df_traverse.iterrows():
        rad = math.radians(row['WCB_deg'])
        de = row['Distance_m'] * math.sin(rad)
        dn = row['Distance_m'] * math.cos(rad)
        raw_de.append(de)
        raw_dn.append(dn)
        
    misclosure_e = sum(raw_de)
    misclosure_n = sum(raw_dn)
    linear_misclosure = math.hypot(misclosure_e, misclosure_n)
    relative_precision = total_dist / linear_misclosure if linear_misclosure > 0 else float('inf')
    
    # Legal Class Assessment (Zambian Standards)
    if relative_precision >= 12000:
        precision_class = "Class A (Primary Cadastral >= 1:12,000)"
    elif relative_precision >= 8000:
        precision_class = "Class B (Secondary Cadastral >= 1:8,000)"
    elif relative_precision >= 4000:
        precision_class = "Class C (Tertiary/Suburban >= 1:4,000)"
    else:
        precision_class = "Unacceptable (Below Legal Precision < 1:4,000)"

    # 2. Compute Bowditch Corrections & Adjusted Coordinates
    curr_e, curr_n = start_e, start_n
    coords = [(curr_e, curr_n)]
    
    for i, row in df_traverse.iterrows():
        dist = row['Distance_m']
        corr_e = -misclosure_e * (dist / total_dist)
        corr_n = -misclosure_n * (dist / total_dist)
        adj_de = raw_de[i] + corr_e
        adj_dn = raw_dn[i] + corr_n
        
        next_e = curr_e + adj_de
        next_n = curr_n + adj_dn
        
        records.append({
            'Leg': row['Leg'],
            'Distance (m)': dist,
            'WCB': deg_to_dms(row['WCB_deg']),
            'Raw ΔE (m)': raw_de[i],
            'Raw ΔN (m)': raw_dn[i],
            'Corr ΔE (m)': corr_e,
            'Corr ΔN (m)': corr_n,
            'Adj ΔE (m)': adj_de,
            'Adj ΔN (m)': adj_dn,
            'Easting (m)': next_e,
            'Northing (m)': next_n
        })
        curr_e, curr_n = next_e, next_n
        coords.append((curr_e, curr_n))
        
    res_df = pd.DataFrame(records)
    return res_df, misclosure_e, misclosure_n, linear_misclosure, relative_precision, precision_class, coords

def helmert_2d_transformation(src_p1, tgt_p1, src_p2, tgt_p2, points_to_transform):
    """
    Computes 2D Helmert 4-Parameter Transformation parameters and transforms source points.
    E' = cE + a*E - b*N
    N' = cN + b*E + a*N
    """
    x1, y1 = src_p1
    x2, y2 = src_p2
    X1, Y1 = tgt_p1
    X2, Y2 = tgt_p2
    
    dx = x2 - x1
    dy = y2 - y1
    dX = X2 - X1
    dY = Y2 - Y1
    
    denom = dx**2 + dy**2
    if denom == 0:
        return None, None
    
    a = (dx * dX + dy * dY) / denom
    b = (dx * dY - dy * dX) / denom
    cE = X1 - a * x1 + b * y1
    cN = Y1 - b * x1 - a * y1
    
    scale = math.hypot(a, b)
    rotation_deg = math.degrees(math.atan2(b, a))
    
    transformed_points = []
    for px, py in points_to_transform:
        Tx = cE + a * px - b * py
        Ty = cN + b * px + a * py
        transformed_points.append((Tx, Ty))
        
    params = {'a': a, 'b': b, 'cE': cE, 'cN': cN, 'scale': scale, 'rotation_deg': rotation_deg}
    return params, transformed_points

def _pdf_safe_text(val):
    """Sanitizes strings for core Latin-1 PDF fonts."""
    text = str(val)
    replacements = {
        "°": " deg ",
        "Δ": "d",
        "²": "^2",
        "θ": "theta",
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "’": "'",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="replace").decode("latin-1")

def _format_cell(val):
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return _pdf_safe_text(val)
        return f"{val:.3f}"
    return _pdf_safe_text(val)

def generate_full_pdf_report(sections):
    """
    Builds a multi-section PDF containing all provided summary lines and DataFrames.
    sections: list of dicts with keys:
      - 'title': str
      - 'summary': list[str] (optional)
      - 'tables': list[tuple[str, pd.DataFrame]]
    """
    class SurveyPDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 13)
            self.cell(0, 8, "ZAMBIAN CADASTRAL SURVEY COMPUTATION REPORT", new_x="LMARGIN", new_y="NEXT", align="C")
            self.set_font("Helvetica", "I", 9)
            self.cell(0, 5, "GE500 Topic 1.4: Traverse, Shoelace Area & 2D Helmert Transformation", new_x="LMARGIN", new_y="NEXT", align="C")
            self.line(10, 24, 287, 24)
            self.ln(5)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "I", 8)
            self.cell(0, 8, f"Page {self.page_no()}", align="C")

    pdf = SurveyPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    usable_w = pdf.w - pdf.l_margin - pdf.r_margin

    def write_dataframe_table(table_title, df):
        if df is None or df.empty:
            return
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, _pdf_safe_text(table_title), new_x="LMARGIN", new_y="NEXT")

        cols = [str(c) for c in df.columns]
        n_cols = max(len(cols), 1)
        col_w = usable_w / n_cols

        def draw_table_header():
            pdf.set_font("Helvetica", "B", 7.5)
            pdf.set_fill_color(230, 235, 242)
            for c in cols:
                pdf.cell(col_w, 6, _pdf_safe_text(c)[:26], border=1, fill=True)
            pdf.ln()

        draw_table_header()
        pdf.set_font("Helvetica", "", 7.5)
        for _, row in df.iterrows():
            if pdf.get_y() + 6 > pdf.h - pdf.b_margin:
                pdf.add_page()
                draw_table_header()
                pdf.set_font("Helvetica", "", 7.5)
            for c in df.columns:
                cell_txt = _format_cell(row[c])
                pdf.cell(col_w, 5.5, cell_txt[:28], border=1)
            pdf.ln()
        pdf.ln(4)

    for sec in sections:
        if pdf.get_y() + 16 > pdf.h - pdf.b_margin:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, _pdf_safe_text(sec["title"]), new_x="LMARGIN", new_y="NEXT")

        for line in sec.get("summary", []):
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(0, 5.5, _pdf_safe_text(line), new_x="LMARGIN", new_y="NEXT")
        if sec.get("summary"):
            pdf.ln(2)

        for t_title, t_df in sec.get("tables", []):
            write_dataframe_table(t_title, t_df)

        pdf.ln(3)

    return bytes(pdf.output())

# --- APP LAYOUT (TABS) ---
tab1, tab2, tab3 = st.tabs([
    "Traverse Computation & Bowditch",
    "Shoelace Area Engine",
    "2D Helmert Transformation"
])

report_sections = []

# ==========================================
# TAB 1: TRAVERSE COMPUTATION & BOWDITCH
# ==========================================
with tab1:
    st.header("Traverse Computation & Bowditch Adjustment")
    
    # INPUT MODE SELECTION (Cycle options without removing coordinates!)
    input_mode = st.radio(
        "Select Input Data Mode:",
        ["Mode A: Coordinate Inputs (Direct Easting/Northing)",
         "Mode B: Bearings & Distances Inputs",
         "Mode C: Interior Angles & Distances Inputs"],
        horizontal=True
    )
    
    st.markdown("---")
    tab1_tables = []
    tab1_summary = [f"Input Mode: {input_mode}"]
    
    if "Mode A" in input_mode:
        st.subheader("1. Enter Station Coordinates (Closed Loop)")
        default_coords = pd.DataFrame({
            "Station": ["STN_1", "STN_2", "STN_3", "STN_4"],
            "Easting (m)": [1000.000, 1250.000, 1250.000, 1000.000],
            "Northing (m)": [2000.000, 2000.000, 2300.000, 2300.000]
        })
        edited_df = st.data_editor(default_coords, num_rows="dynamic", use_container_width=True)
        tab1_tables.append(("Input Station Coordinates (Mode A)", edited_df))
        
        if len(edited_df) >= 3:
            coords_list = list(zip(edited_df["Easting (m)"], edited_df["Northing (m)"]))
            # Derive bearings and distances for Bowditch evaluation
            legs = []
            for i in range(len(coords_list)):
                nxt = (i + 1) % len(coords_list)
                e1, n1 = coords_list[i]
                e2, n2 = coords_list[nxt]
                stn1 = edited_df["Station"].iloc[i]
                stn2 = edited_df["Station"].iloc[nxt]
                _, _, dist, wcb, _ = calculate_join(e1, n1, e2, n2)
                legs.append({"Leg": f"{stn1}->{stn2}", "Distance_m": dist, "WCB_deg": wcb})
            df_legs = pd.DataFrame(legs)
            start_e, start_n = coords_list[0][0], coords_list[0][1]
            
    elif "Mode B" in input_mode:
        st.subheader("1. Enter Leg Bearings & Distances")
        col_start1, col_start2 = st.columns(2)
        start_e = col_start1.number_input("Starting Easting E0 (m)", value=1000.000, format="%.3f")
        start_n = col_start2.number_input("Starting Northing N0 (m)", value=2000.000, format="%.3f")
        
        default_legs = pd.DataFrame({
            "Leg": ["1->2", "2->3", "3->4", "4->1"],
            "Distance_m": [250.000, 300.000, 250.000, 300.000],
            "WCB_deg": [90.0, 0.0, 270.0, 180.0]
        })
        df_legs = st.data_editor(default_legs, num_rows="dynamic", use_container_width=True)
        tab1_summary.append(f"Starting Coordinates: E0 = {start_e:.3f} m, N0 = {start_n:.3f} m")
        tab1_tables.append(("Input Leg Bearings & Distances (Mode B)", df_legs))
        
    else:  # Mode C
        st.subheader("1. Enter Baseline Bearing, Interior Angles & Distances")
        col_c1, col_c2, col_c3 = st.columns(3)
        start_e = col_c1.number_input("Start Easting E0 (m)", value=1000.000, format="%.3f", key="c_e")
        start_n = col_c2.number_input("Start Northing N0 (m)", value=2000.000, format="%.3f", key="c_n")
        init_wcb = col_c3.number_input("Initial Reference Bearing (°)", value=90.0, format="%.4f")
        
        default_angles = pd.DataFrame({
            "Station": ["STN_1", "STN_2", "STN_3", "STN_4"],
            "Distance_to_Next (m)": [250.000, 300.000, 250.000, 300.000],
            "Interior_Angle (deg)": [90.0, 90.0, 90.0, 90.0]
        })
        df_angles = st.data_editor(default_angles, num_rows="dynamic", use_container_width=True)
        tab1_summary.append(f"Start: E0 = {start_e:.3f} m, N0 = {start_n:.3f} m | Initial Bearing: {init_wcb:.4f} deg")
        tab1_tables.append(("Input Angles & Distances (Mode C)", df_angles))
        
        # Propagate bearings from angles
        legs = []
        curr_bearing = init_wcb
        for i in range(len(df_angles)):
            dist = df_angles["Distance_to_Next (m)"].iloc[i]
            stn1 = df_angles["Station"].iloc[i]
            nxt_idx = (i + 1) % len(df_angles)
            stn2 = df_angles["Station"].iloc[nxt_idx]
            legs.append({"Leg": f"{stn1}->{stn2}", "Distance_m": dist, "WCB_deg": curr_bearing})
            angle = df_angles["Interior_Angle (deg)"].iloc[i]
            curr_bearing = (curr_bearing + 180 - angle + 360) % 360
        df_legs = pd.DataFrame(legs)

    # PROCESS BOWDITCH COMPUTATION
    if 'df_legs' in locals() and len(df_legs) >= 3:
        st.markdown("---")
        st.subheader("2. Bowditch Adjustment Results")
        
        res_df, mis_e, mis_n, lin_mis, rel_prec, prec_cls, adjusted_coords = bowditch_traverse_adjustment(df_legs, start_e, start_n)
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Linear Misclosure (e)", f"{lin_mis:.4f} m")
        m2.metric("Relative Precision", f"1 : {int(rel_prec):,}")
        m3.metric("ΔE Misclosure", f"{mis_e:+.4f} m")
        m4.metric("ΔN Misclosure", f"{mis_n:+.4f} m")
        
        st.info(f"**Zambian Legal Standards Evaluation:** {prec_cls}")
        st.dataframe(res_df, use_container_width=True)
        
        # Calculate Parcel Area
        area_sqm = calculate_shoelace_area(adjusted_coords)
        area_ha = area_sqm / 10000.0

        tab1_summary.extend([
            f"Linear Misclosure (e): {lin_mis:.4f} m | Relative Precision: 1:{int(rel_prec):,}",
            f"dE Misclosure: {mis_e:+.4f} m | dN Misclosure: {mis_n:+.4f} m",
            f"Zambian Legal Standards Evaluation: {prec_cls}",
            f"Adjusted Parcel Area: {area_sqm:,.3f} m^2 ({area_ha:,.4f} ha)"
        ])
        tab1_tables.append(("Bowditch Adjusted Traverse Table", res_df))
        
        st.markdown("---")
        st.subheader("3. Adjusted Parcel Area & Interactive Map")
        a_col1, a_col2 = st.columns(2)
        a_col1.metric("Parcel Area (m²)", f"{area_sqm:,.3f} m²")
        a_col2.metric("Parcel Area (Hectares)", f"{area_ha:,.4f} ha")
        
        # Render Map
        lats, lons = [], []
        base_lat, base_lon = -12.8000, 28.2000
        for e, n in adjusted_coords:
            lats.append(base_lat + (n - start_n) / 111000.0)
            lons.append(base_lon + (e - start_e) / 108000.0)
            
        map_center = [sum(lats)/len(lats), sum(lons)/len(lons)]
        m = folium.Map(location=map_center, zoom_start=16)
        poly_pts = list(zip(lats, lons))
        folium.Polygon(locations=poly_pts, color="crimson", weight=3, fill=True, fill_opacity=0.3).add_to(m)
        for idx, (lat, lon) in enumerate(poly_pts[:-1]):
            folium.Marker([lat, lon], popup=f"Station {idx+1}", icon=folium.Icon(color="blue")).add_to(m)
            
        components.html(m._repr_html_(), height=400)

    report_sections.append({
        "title": "1. Traverse Computation & Bowditch Adjustment",
        "summary": tab1_summary,
        "tables": tab1_tables
    })

# ==========================================
# TAB 2: SHOELACE AREA ENGINE
# ==========================================
with tab2:
    st.header("Polygon Area Engine (Gauss Shoelace Formula)")
    st.write("Compute the rectilinear area of any parcel directly from coordinate pairs.")
    
    area_df = st.data_editor(
        pd.DataFrame({
            "Corner Point": ["P1", "P2", "P3", "P4", "P5"],
            "Easting (m)": [4500.0, 4750.0, 4800.0, 4600.0, 4450.0],
            "Northing (m)": [8000.0, 8050.0, 7850.0, 7700.0, 7800.0]
        }),
        num_rows="dynamic",
        use_container_width=True,
        key="shoelace_editor"
    )

    tab2_summary = []
    tab2_tables = [("Shoelace Parcel Coordinates", area_df)]
    
    sh_coords = list(zip(area_df["Easting (m)"], area_df["Northing (m)"]))
    if len(sh_coords) >= 3:
        calc_area_sqm = calculate_shoelace_area(sh_coords)
        calc_area_ha = calc_area_sqm / 10000.0
        
        res1, res2 = st.columns(2)
        res1.metric("Calculated Area (m²)", f"{calc_area_sqm:,.2f} m²")
        res2.metric("Calculated Area (Hectares)", f"{calc_area_ha:,.4f} ha")
        tab2_summary.append(f"Calculated Area: {calc_area_sqm:,.2f} m^2 ({calc_area_ha:,.4f} ha)")

    report_sections.append({
        "title": "2. Shoelace Area Engine",
        "summary": tab2_summary,
        "tables": tab2_tables
    })

# ==========================================
# TAB 3: 2D HELMERT TRANSFORMATION
# ==========================================
with tab3:
    st.header("2D Helmert 4-Parameter Coordinate Transformation")
    st.write("Transform local or baseline survey coordinates into National Grid / WGS84 coordinates.")
    
    st.subheader("1. Enter Common Control Points (Minimum 2 Points)")
    h_col1, h_col2 = st.columns(2)
    with h_col1:
        st.markdown("**Control Point 1**")
        src_e1 = st.number_input("Source E1", value=100.000, format="%.3f")
        src_n1 = st.number_input("Source N1", value=200.000, format="%.3f")
        tgt_e1 = st.number_input("Target E1", value=500105.200, format="%.3f")
        tgt_n1 = st.number_input("Target N1", value=8580210.500, format="%.3f")
        
    with h_col2:
        st.markdown("**Control Point 2**")
        src_e2 = st.number_input("Source E2", value=350.000, format="%.3f")
        src_n2 = st.number_input("Source N2", value=450.000, format="%.3f")
        tgt_e2 = st.number_input("Target E2", value=500355.800, format="%.3f")
        tgt_n2 = st.number_input("Target N2", value=8580460.900, format="%.3f")

    st.subheader("2. Enter Source Points to Transform")
    src_pts_df = st.data_editor(
        pd.DataFrame({
            "Point Name": ["Corner_A", "Corner_B", "Corner_C"],
            "Source Easting (m)": [150.000, 220.000, 300.000],
            "Source Northing (m)": [250.000, 310.000, 400.000]
        }),
        num_rows="dynamic",
        use_container_width=True
    )

    control_pts_df = pd.DataFrame({
        "Control Point": ["CP1", "CP2"],
        "Source E (m)": [src_e1, src_e2],
        "Source N (m)": [src_n1, src_n2],
        "Target E (m)": [tgt_e1, tgt_e2],
        "Target N (m)": [tgt_n1, tgt_n2]
    })
    tab3_summary = []
    tab3_tables = [
        ("Common Control Points", control_pts_df),
        ("Source Points to Transform", src_pts_df)
    ]
    
    pts_to_tx = list(zip(src_pts_df["Source Easting (m)"], src_pts_df["Source Northing (m)"]))
    params, tx_results = helmert_2d_transformation((src_e1, src_n1), (tgt_e1, tgt_n1), (src_e2, src_n2), (tgt_e2, tgt_n2), pts_to_tx)
    
    if params:
        st.markdown("---")
        st.subheader("3. Transformation Parameters & Results")
        p1, p2, p3 = st.columns(3)
        p1.metric("Scale Factor (s)", f"{params['scale']:.6f}")
        p2.metric("Rotation Angle (θ)", f"{params['rotation_deg']:.4f}°")
        p3.metric("Shifts (cE, cN)", f"{params['cE']:,.2f} m, {params['cN']:,.2f} m")
        
        out_records = []
        for i, (tx_e, tx_n) in enumerate(tx_results):
            out_records.append({
                "Point Name": src_pts_df["Point Name"].iloc[i],
                "Source Easting": src_pts_df["Source Easting (m)"].iloc[i],
                "Source Northing": src_pts_df["Source Northing (m)"].iloc[i],
                "Transformed Easting (m)": tx_e,
                "Transformed Northing (m)": tx_n
            })
        tx_out_df = pd.DataFrame(out_records)
        st.dataframe(tx_out_df, use_container_width=True)

        tab3_summary.append(
            f"Scale Factor: {params['scale']:.6f} | Rotation: {params['rotation_deg']:.4f} deg | "
            f"Shifts (cE, cN): {params['cE']:,.2f} m, {params['cN']:,.2f} m"
        )
        tab3_tables.append(("Transformed Coordinates", tx_out_df))

    report_sections.append({
        "title": "3. 2D Helmert Transformation",
        "summary": tab3_summary,
        "tables": tab3_tables
    })

# --- PDF REPORT EXPORT ---
st.markdown("---")
st.subheader("Export Full PDF Report")
st.write("Generate a PDF report containing all computation tables and summary results across the tabs.")
pdf_bytes = generate_full_pdf_report(report_sections)
st.download_button(
    label="Download Full Survey Report (PDF)",
    data=pdf_bytes,
    file_name="Zambian_Cadastral_Survey_Report.pdf",
    mime="application/pdf"
)
