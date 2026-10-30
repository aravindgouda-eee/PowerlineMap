import base64
import html
import mimetypes
from pathlib import Path

import folium
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent
IMAGES_DIR = PROJECT_DIR / "images"
API_BASE_URL = "https://telanganapowerlinemap.fastapicloud.dev"

st.set_page_config(
    page_title="Telangana Power Infrastructure Map",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ Telangana Power Infrastructure Map")

st.caption(
    "Interactive map of power stations, substations, "
    "transmission lines, and distribution infrastructure."
)


# ============================================================
# API DATA
# ============================================================

@st.cache_data(ttl=10)
def fetch_data(endpoint):
    try:
        response = requests.get(
            f"{API_BASE_URL}/{endpoint}",
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            return data, None

        if isinstance(data, dict):
            for key in (
                "locations",
                "lines",
                "power_lines",
                "data",
                "results",
            ):
                if isinstance(data.get(key), list):
                    return data[key], None

            return [], f"Unexpected data format from /{endpoint}"

        return [], f"Unexpected response from /{endpoint}"

    except requests.RequestException as exc:
        return [], str(exc)


def safe_text(value, default="Not specified"):
    if value is None:
        return default

    result = str(value).strip()

    if result.lower() in ("", "none", "null", "nan"):
        return default

    return result


def valid_coordinates(record):
    try:
        latitude = float(record["latitude"])
        longitude = float(record["longitude"])

        if not (-90 <= latitude <= 90):
            return None

        if not (-180 <= longitude <= 180):
            return None

        return latitude, longitude

    except (KeyError, TypeError, ValueError):
        return None


def voltage_display(value, unit="kV"):
    voltage = safe_text(value, "")

    if not voltage:
        return "Not verified"

    return f"{voltage} {unit} (provisional)"


def location_voltage(location):
    location_type = safe_text(
        location.get("location_type"), ""
    ).lower()

    unit = "V" if location_type == "consumer" else "kV"

    return voltage_display(
        location.get("voltage_kv"),
        unit,
    )


def line_voltage(line):
    line_type = safe_text(
        line.get("line_type"), ""
    ).lower()

    unit = "V" if "consumer" in line_type else "kV"

    return voltage_display(
        line.get("voltage_kv"),
        unit,
    )


def safe_image_path(relative_path):
    relative_path = safe_text(relative_path, "")

    if not relative_path:
        return None

    candidate = (PROJECT_DIR / relative_path).resolve()

    try:
        candidate.relative_to(IMAGES_DIR.resolve())
    except ValueError:
        return None

    if candidate.is_file():
        return candidate

    return None


def image_data_uri(relative_path):
    image_path = safe_image_path(relative_path)

    if image_path is None:
        return None

    mime_type, _ = mimetypes.guess_type(str(image_path))

    if not mime_type or not mime_type.startswith("image/"):
        return None

    try:
        encoded = base64.b64encode(
            image_path.read_bytes()
        ).decode("ascii")

        return f"data:{mime_type};base64,{encoded}"

    except OSError:
        return None


# ============================================================
# FETCH LOCATIONS AND POWER LINES
# ============================================================

locations, locations_error = fetch_data("locations")
lines, lines_error = fetch_data("lines")

if locations_error or lines_error:
    st.error(
        "Unable to load data from FastAPI. "
        "Make sure the API is running."
    )

    if locations_error:
        st.write("Locations:", locations_error)

    if lines_error:
        st.write("Power lines:", lines_error)

    st.code(
        "python -m uvicorn api:app --reload",
        language="powershell",
    )

    st.stop()


# ============================================================
# MAP FILTERS
# ============================================================

st.subheader("Interactive Power Infrastructure Map")

location_types = sorted({
    safe_text(
        location.get("location_type"),
        "Not specified",
    )
    for location in locations
})

filter_col, line_col = st.columns([3, 1])

with filter_col:
    selected_types = st.multiselect(
        "Filter by location type",
        options=location_types,
        default=location_types,
    )

with line_col:
    show_connections = st.checkbox(
        "Show illustrative power-flow lines",
        value=True,
    )


# ============================================================
# FILTER LOCATIONS
# ============================================================

filtered_locations = [
    location
    for location in locations
    if safe_text(
        location.get("location_type"),
        "Not specified",
    ) in selected_types
    and valid_coordinates(location) is not None
]

visible_location_ids = {
    safe_text(location.get("location_id"), "")
    for location in filtered_locations
}

location_lookup = {
    safe_text(location.get("location_id"), ""): location
    for location in locations
}


# ============================================================
# CREATE MAP
# ============================================================

all_coordinates = [
    valid_coordinates(location)
    for location in filtered_locations
]

all_coordinates = [
    coordinates
    for coordinates in all_coordinates
    if coordinates is not None
]

if all_coordinates:
    center_lat = sum(
        point[0] for point in all_coordinates
    ) / len(all_coordinates)

    center_lon = sum(
        point[1] for point in all_coordinates
    ) / len(all_coordinates)

else:
    center_lat, center_lon = 17.8, 79.1

power_map = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=7,
    control_scale=True,
    tiles="OpenStreetMap",
)

marker_colors = {
    "generation": "green",
    "power evacuation": "red",
    "transmission": "blue",
    "distribution": "orange",
    "consumer": "purple",
}


# ============================================================
# LOCATION POPUP
# ============================================================

def make_location_popup(location):
    name = html.escape(
        safe_text(location.get("name"), "Unnamed location")
    )

    location_type = html.escape(
        safe_text(location.get("location_type"))
    )

    voltage = html.escape(location_voltage(location))

    details = html.escape(
        safe_text(
            location.get("details"),
            "No details available",
        )
    )

    image_uri = image_data_uri(
        location.get("image_path")
    )

    image_html = ""

    if image_uri:
        image_html = f"""
        <img src="{image_uri}"
             alt="{name}"
             style="width:100%;max-width:280px;
                    max-height:170px;object-fit:cover;
                    border-radius:5px;margin:8px 0;">
        """

    popup_content = f"""
    <div style="width:270px;max-width:100%;
                font-family:Arial,sans-serif;
                font-size:14px;line-height:1.5;">

        <h3 style="margin:0 0 8px 0;color:#24364b;">
            {name}
        </h3>

        {image_html}

        <b>Function:</b> {location_type}<br>
        <b>Voltage:</b> {voltage}<br>

        <p>{details}</p>
    </div>
    """

    return folium.Popup(
        popup_content,
        max_width=320,
    )


# ============================================================
# ADD LOCATION MARKERS
# ============================================================

for location in filtered_locations:
    coordinates = valid_coordinates(location)

    if coordinates is None:
        continue

    location_type = safe_text(
        location.get("location_type"), ""
    )

    color = marker_colors.get(
        location_type.lower(),
        "cadetblue",
    )

    folium.Marker(
        location=coordinates,
        tooltip=safe_text(
            location.get("name"),
            "Power location",
        ),
        popup=make_location_popup(location),
        icon=folium.Icon(
            color=color,
            icon="flash",
            prefix="fa",
        ),
    ).add_to(power_map)


# ============================================================
# DRAW PLAIN RED POWER-FLOW LINES
# No line popups, descriptions, tooltips, or click interaction.
# ============================================================

drawn_lines = 0

if show_connections:

    for line in lines:
        from_id = safe_text(
            line.get("from_location_id"), ""
        )

        to_id = safe_text(
            line.get("to_location_id"), ""
        )

        # Find the connected locations.
        from_location = location_lookup.get(from_id)
        to_location = location_lookup.get(to_id)

        if from_location is None or to_location is None:
            continue

        # Respect the location-type filters.
        if (
            from_id not in visible_location_ids
            or to_id not in visible_location_ids
        ):
            continue

        # Read coordinates from the API records.
        start = valid_coordinates(from_location)
        end = valid_coordinates(to_location)

        if start is None or end is None:
            continue

        # Add a plain solid red line.
        folium.PolyLine(
            locations=[start, end],
            color="red",
            weight=3,
            opacity=0.9,
            interactive=False,
        ).add_to(power_map)

        drawn_lines += 1


# ============================================================
# FIT MAP TO LOCATIONS
# ============================================================

if all_coordinates:
    power_map.fit_bounds(
        all_coordinates,
        padding=(35, 35),
    )


# ============================================================
# DISPLAY MAP
# ============================================================

st.subheader("Map View")

if not filtered_locations:
    st.warning(
        "No locations match the selected filters. "
        "Select at least one location type."
    )

else:
    map_html = power_map.get_root().render()

    components.html(
        map_html,
        height=650,
        scrolling=False,
    )

st.caption(
    "Lines show illustrative connections between supplied "
    "coordinates, not verified physical cable routes."
)


# ============================================================
# DATA TABLE TABS
# ============================================================

tab_locations, tab_lines = st.tabs([
    "📍 Locations",
    "🔌 Power-Line Connections",
])


# ============================================================
# LOCATIONS TAB
# ============================================================

with tab_locations:
    st.subheader("Power Locations")

    if locations:
        location_rows = []

        for location in locations:
            coordinates = valid_coordinates(location)

            location_rows.append({
                "Location ID": location.get("location_id"),
                "Name": location.get("name"),
                "Function": location.get("location_type"),
                "Voltage": location_voltage(location),
                "Latitude": (
                    coordinates[0] if coordinates else None
                ),
                "Longitude": (
                    coordinates[1] if coordinates else None
                ),
                "Coordinate Status": location.get(
                    "coordinate_status"
                ),
                "Details": location.get("details"),
            })

        locations_df = pd.DataFrame(location_rows)

        st.dataframe(
            locations_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download Locations CSV",
            data=locations_df.to_csv(
                index=False
            ).encode("utf-8"),
            file_name="telangana_power_locations.csv",
            mime="text/csv",
        )

    else:
        st.info("No location records are available.")


# ============================================================
# POWER-LINE CONNECTIONS TAB
# ============================================================

with tab_lines:
    st.subheader("Power-Line Connections")

    if lines:
        line_rows = []

        for line in lines:
            from_location = location_lookup.get(
                safe_text(
                    line.get("from_location_id"), ""
                )
            )

            to_location = location_lookup.get(
                safe_text(
                    line.get("to_location_id"), ""
                )
            )

            line_rows.append({
                "Line ID": line.get("line_id"),
                "Line Name": line.get("line_name"),
                "From": (
                    from_location.get("name")
                    if from_location
                    else line.get("from_location_id")
                ),
                "To": (
                    to_location.get("name")
                    if to_location
                    else line.get("to_location_id")
                ),
                "Voltage": line_voltage(line),
                "Line Type": line.get("line_type"),
                "Route Status": line.get("route_status"),
            })

        lines_df = pd.DataFrame(line_rows)

        st.dataframe(
            lines_df,
            use_container_width=True,
            hide_index=True,
        )

        st.warning(
            "Line routes, voltage ratings, and electrical connections "
            "must be verified against official records before "
            "engineering use."
        )

        st.download_button(
            "Download Power Lines CSV",
            data=lines_df.to_csv(
                index=False
            ).encode("utf-8"),
            file_name="telangana_power_lines.csv",
            mime="text/csv",
        )

    else:
        st.info("No power-line records are available.")


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Telangana Power Infrastructure Map | "
    "Data provided by the local FastAPI backend. "
    "Coordinates, voltage ratings, and routes require verification."
)