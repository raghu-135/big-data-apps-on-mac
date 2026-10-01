import streamlit as st
import docker
import os
import re
from collections import defaultdict
from pathlib import Path

st.set_page_config(page_title="Docker Service Manager", layout="wide")

client = docker.from_env()

# Mounted read-only via `-v ../:/apps` in the webui Makefile; each subfolder is a service project.
APPS_DIR = Path(os.environ.get("APPS_DIR", "/apps"))
EXCLUDED_DIRS = {"scripts", "jinja2"}

MAX_OPEN_LOG_PANELS = 4   # caps concurrently rendered log panels so the UI stays responsive
LOG_TAIL = 200
MAX_LOG_CHARS = 20000     # hard cap on rendered log text regardless of tail, keeps the DOM light

@st.cache_data(ttl=30)
def get_app_service_names():
    if not APPS_DIR.is_dir():
        return set()
    return {
        p.name for p in APPS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in EXCLUDED_DIRS
    }

def render_services_section():
    st.header('Services')
    service_names = sorted(get_app_service_names())
    if not service_names:
        st.info(f"No service folders found under {APPS_DIR}.")
        return
    st.caption("Copy a command and run it from a terminal at the repo root.")
    for name in service_names:
        with st.expander(name, expanded=False):
            st.code(f"cd apps/{name} && make up", language="bash")
            st.code(f"cd apps/{name} && make down", language="bash")

def is_app_container(name, project, service_names):
    if project in service_names:
        return True
    # Containers started outside Compose (e.g. webui itself) are matched by name.
    return name in service_names

@st.cache_data(ttl=3)
def get_containers():
    service_names = get_app_service_names()
    containers = []
    for c in client.containers.list(all=True):
        project = c.labels.get('com.docker.compose.project')
        if service_names and not is_app_container(c.name, project, service_names):
            continue
        containers.append({
            'id': c.id,
            'name': c.name,
            'image': c.image.tags[0] if c.image.tags else str(c.image),
        })
    return containers

def _truncate(text):
    if len(text) > MAX_LOG_CHARS:
        return f"...[truncated, showing last {MAX_LOG_CHARS} chars]...\n" + text[-MAX_LOG_CHARS:]
    return text

@st.cache_data(ttl=4)
def _fetch_raw_logs(cid, tail, timestamps):
    return client.containers.get(cid).logs(tail=tail, timestamps=timestamps).decode('utf-8', errors='replace')

def get_container_logs(cid, tail=LOG_TAIL):
    try:
        logs = _fetch_raw_logs(cid, tail, False)
    except Exception as e:
        return f"Error fetching logs: {e}"
    return _truncate(logs)

def get_merged_group_logs(group_containers, tail=LOG_TAIL):
    # Docker has no multi-container log API; fetch each with timestamps and interleave, like `docker compose logs`.
    entries = []
    for c in group_containers:
        try:
            raw = _fetch_raw_logs(c['id'], tail, True)
        except Exception as e:
            entries.append(("", f"[{c['name']}] Error fetching logs: {e}"))
            continue
        for line in raw.splitlines():
            if not line:
                continue
            ts, _, rest = line.partition(' ')
            entries.append((ts, f"[{c['name']}] {rest}"))
    # RFC3339Nano timestamps are fixed-width UTC strings, so lexicographic sort == chronological sort.
    entries.sort(key=lambda e: e[0])
    return _truncate("\n".join(text for _, text in entries))

def _open_panel_order():
    return st.session_state.setdefault('_open_log_panels', [])

def _toggle_panel(state_key):
    """Flip a log panel's visibility, evicting the oldest-opened panel past MAX_OPEN_LOG_PANELS.
    Returns True if another panel was force-closed (needs a full rerun to reflect everywhere)."""
    is_open = not st.session_state.get(state_key, False)
    st.session_state[state_key] = is_open
    order = _open_panel_order()
    if state_key in order:
        order.remove(state_key)
    if not is_open:
        return False
    order.append(state_key)
    evicted = False
    while len(order) > MAX_OPEN_LOG_PANELS:
        oldest = order.pop(0)
        st.session_state[oldest] = False
        evicted = True
    return evicted


def main():
    st.title('Docker Service Manager')
    st.markdown('Manage your Docker containers visually')
    st.caption(f"Up to {MAX_OPEN_LOG_PANELS} log panels can be open at once; opening another closes the oldest.")

    render_services_section()

    st.header('Docker Containers')
    if not get_app_service_names():
        st.warning(f"Could not read service folders from {APPS_DIR}; showing all host containers.")
    containers = get_containers()

    if not containers:
        st.info('No containers found.')
        return

    # Group containers by the first part of their image (before colon or dash)
    groups = defaultdict(list)
    for c in containers:
        m = re.match(r"([\w\-/]+?)[-:].*", c['image'])
        group = m.group(1) if m else c['image']
        groups[group].append(c)

    for group_name in sorted(groups.keys()):
        group_containers = groups[group_name]
        with st.expander(f"{group_name} ({len(group_containers)})", expanded=True):
            if len(group_containers) > 1:
                render_group_logs_panel(group_name, group_containers)
            for c in group_containers:
                render_container_row(c['id'], c['name'], c['image'])


@st.fragment
def render_group_logs_panel(group_name, group_containers):
    # Fragment-scoped: toggling combined logs only reruns this panel, not the whole page.
    state_key = f"show_group_logs_{group_name}"
    is_open = st.session_state.get(state_key, False)
    label = f"{'Hide' if is_open else 'Show'} Combined Logs for {group_name} ({len(group_containers)} containers)"
    if st.button(label, key=f"btn_{state_key}"):
        evicted = _toggle_panel(state_key)
        st.rerun(scope="app" if evicted else "fragment")

    if st.session_state.get(state_key, False):
        st.text_area(
            f"Combined Logs: {group_name}",
            get_merged_group_logs(group_containers),
            height=500,
            key=f"group_logs_area_{group_name}",
            disabled=True
        )
    st.divider()


@st.fragment
def render_container_row(cid, name, image):
    # Fragment-scoped: start/stop/restart/logs here never re-lists all containers or other panels.
    try:
        status = client.containers.get(cid).status
    except Exception:
        status = "unknown"

    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(name)
        st.write(f"Image: {image}")
        status_color = {'running': 'green', 'exited': 'red', 'paused': 'orange'}.get(status, 'grey')
        st.markdown(f"<span style='color:{status_color};font-weight:bold;'>Status: {status.capitalize()}</span>", unsafe_allow_html=True)
    with col2:
        if status == 'running':
            if st.button(f"Stop {name}", key=f"stop_{cid}"):
                client.containers.get(cid).stop()
                st.rerun(scope="fragment")
            if st.button(f"Restart {name}", key=f"restart_{cid}"):
                client.containers.get(cid).restart()
                st.rerun(scope="fragment")
        else:
            if st.button(f"Start {name}", key=f"start_{cid}"):
                client.containers.get(cid).start()
                st.rerun(scope="fragment")

    log_state_key = f"show_logs_{cid}"
    is_open = st.session_state.get(log_state_key, False)
    if st.button(f"{'Hide' if is_open else 'Show'} Logs for {name}", key=f"btn_show_logs_{cid}"):
        evicted = _toggle_panel(log_state_key)
        st.rerun(scope="app" if evicted else "fragment")

    if st.session_state.get(log_state_key, False):
        st.text_area(
            f"Logs: {name}",
            get_container_logs(cid),
            height=400,
            key=f"logs_area_{cid}",
            disabled=True
        )

if __name__ == "__main__":
    main()