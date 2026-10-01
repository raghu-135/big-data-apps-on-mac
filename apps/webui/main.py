import streamlit as st
import docker
import os
import uuid
from collections import defaultdict
from pathlib import Path

st.set_page_config(page_title="Docker Service Manager", layout="wide")

# DOCKER_HOST (set by the webui Makefile) points at docker-socket-proxy, not the raw socket, so
# docker.from_env() only gets the API sections the proxy grants (see Makefile's socket-proxy target).
client = docker.from_env()
DOCKER_HOST = os.environ.get("DOCKER_HOST")
MGMT_NETWORK = os.environ.get("WEBUI_MGMT_NETWORK", "webui-mgmt-network")

# Mounted at the same absolute path on host and container (see webui Makefile) so Makefile-computed
# paths (APP_DATA_DIR, CONFIGS_DIR, COMPOSE_FILE, ...) stay valid for the host docker daemon.
REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/"))
APPS_DIR = Path(os.environ.get("APPS_DIR", REPO_ROOT / "apps"))
EXCLUDED_DIRS = {"scripts", "jinja2"}
# webui can't safely bring itself up from inside itself.
BRINGUP_EXCLUDED_DIRS = EXCLUDED_DIRS | {"webui"}

RUNNER_IMAGE = "big-data-make-runner:latest"
RUNNER_DOCKERFILE_DIR = Path(__file__).parent / "runner"

LOG_TAIL = 200

@st.cache_data(ttl=30)
def get_app_service_names():
    if not APPS_DIR.is_dir():
        return set()
    return {
        p.name for p in APPS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in EXCLUDED_DIRS
    }

@st.cache_data(ttl=3)
def get_containers_by_service():
    """Containers grouped by service folder name (matched by compose project, or by name for
    non-Compose services like webui) - the single source for both status and container rows."""
    service_names = get_app_service_names()
    by_service = defaultdict(list)
    for c in client.containers.list(all=True):
        project = c.labels.get('com.docker.compose.project')
        matched = project if project in service_names else (c.name if c.name in service_names else None)
        if not matched:
            continue
        by_service[matched].append({
            'id': c.id,
            'name': c.name,
            'image': c.image.tags[0] if c.image.tags else str(c.image),
            'status': c.status,
        })
    return dict(by_service)

def ensure_runner_image():
    try:
        client.images.get(RUNNER_IMAGE)
    except docker.errors.ImageNotFound:
        client.images.build(path=str(RUNNER_DOCKERFILE_DIR), tag=RUNNER_IMAGE, rm=True)


def _run_make_target(service_name, target):
    """Runs `make <target>` for a service in a throwaway runner container (same pattern as `make render`).
    The repo root is bind-mounted at its real host path so Makefile-computed bind mounts resolve
    correctly when the host docker daemon creates them. The runner reaches Docker only through
    docker-socket-proxy (via DOCKER_HOST on MGMT_NETWORK) - it never gets the raw socket. Container
    is left in place (not auto-removed) so its exit code/logs remain inspectable afterwards."""
    ensure_runner_image()
    service_dir = str(REPO_ROOT / "apps" / service_name)
    container = client.containers.run(
        RUNNER_IMAGE,
        command=["make", target],
        working_dir=service_dir,
        network=MGMT_NETWORK,
        environment={
            "DOCKER_HOST": DOCKER_HOST,
            # Classic builder only: buildkit's session/grpc frontend isn't supported by the proxy.
            "DOCKER_BUILDKIT": "0",
        },
        volumes={
            str(REPO_ROOT): {"bind": str(REPO_ROOT), "mode": "rw"},
        },
        name=f"make{target}-{service_name}-{uuid.uuid4().hex[:8]}",
        detach=True,
    )
    return container.id


def start_make_up(service_name):
    return _run_make_target(service_name, "up")


def start_make_down(service_name):
    return _run_make_target(service_name, "down")


def get_make_job_status(cid):
    try:
        c = client.containers.get(cid)
    except docker.errors.NotFound:
        return None
    state = c.attrs.get("State", {})
    return {"running": state.get("Running", False), "exit_code": state.get("ExitCode")}


def get_make_job_logs(cid, tail=300):
    try:
        return client.containers.get(cid).logs(tail=tail).decode("utf-8", errors="replace")
    except Exception as e:
        return f"Error fetching logs: {e}"

@st.cache_data(ttl=4)
def _fetch_raw_logs(cid, tail, timestamps):
    return client.containers.get(cid).logs(tail=tail, timestamps=timestamps).decode('utf-8', errors='replace')

def get_container_logs(cid, tail=LOG_TAIL):
    try:
        return _fetch_raw_logs(cid, tail, False)
    except Exception as e:
        return f"Error fetching logs: {e}"

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
    return "\n".join(text for _, text in entries)

def _toggle_panel(state_key):
    st.session_state[state_key] = not st.session_state.get(state_key, False)


def main():
    st.title('Docker Service Manager')
    st.markdown('Manage your Docker containers visually')

    render_services_section()


def render_services_section():
    st.header('Services')
    service_names = sorted(get_app_service_names())
    if not service_names:
        st.info(f"No service folders found under {APPS_DIR}.")
        return
    st.caption("Each button runs `make up` for that service in the background, which starts its dependencies first.")
    jobs = st.session_state.setdefault('_make_jobs', {})
    containers_by_service = get_containers_by_service()
    running = [n for n in service_names if any(c['status'] == 'running' for c in containers_by_service.get(n, []))]
    offline = [n for n in service_names if n not in running]

    st.subheader(f"Running ({len(running)})")
    if not running:
        st.caption("No services currently running.")
    for name in running:
        render_service_row(name, jobs, True, containers_by_service.get(name, []))

    st.subheader(f"Offline ({len(offline)})")
    if not offline:
        st.caption("All services are running.")
    for name in offline:
        render_service_row(name, jobs, False, containers_by_service.get(name, []))
    st.divider()


@st.fragment
def render_service_row(name, jobs, is_running, containers):
    # Fragment-scoped: polling/launching one service's job never reruns the rest of the page.
    job = jobs.get(name)
    cid = job['cid'] if job else None
    action = job['action'] if job else None
    job_status = get_make_job_status(cid) if cid else None
    busy = bool(job_status and job_status['running'])
    # webui's `make down` also removes docker-socket-proxy, which every service's runner depends on
    # to reach Docker - letting the UI trigger that would break every other button, not just webui's.
    can_manage = name not in BRINGUP_EXCLUDED_DIRS

    name_col, status_col, up_col, stop_col, refresh_col = st.columns([2.5, 1.3, 1, 1, 1.3])
    with name_col:
        st.markdown(f"**{name}**")
    with status_col:
        st.markdown(":green[\u25cf Running]" if is_running else ":gray[\u25cb Offline]")
    with up_col:
        if st.button("Bring up", key=f"bringup_{name}", disabled=busy or not can_manage,
                      help="Runs `make up` in the background, starting dependencies first"):
            jobs[name] = {"cid": start_make_up(name), "action": "up"}
            st.rerun(scope="fragment")
    with stop_col:
        if st.button("Stop", key=f"stop_{name}", disabled=busy or not can_manage,
                      help="Runs `make down` in the background"):
            jobs[name] = {"cid": start_make_down(name), "action": "down"}
            st.rerun(scope="fragment")
    with refresh_col:
        if st.button("Refresh status", key=f"refresh_{name}"):
            st.rerun(scope="fragment")

    if job_status and job_status['running']:
        verb = "Bringing up" if action == "up" else "Bringing down"
        st.caption(f"{verb}... (`make {action}`)")
    elif job_status and job_status['exit_code'] not in (None, 0):
        st.caption(f"Last `make {action}` failed (exit code {job_status['exit_code']})")

    if cid:
        log_state_key = f"show_make_logs_{name}"
        is_open = st.session_state.get(log_state_key, False)
        label_verb = "Bring up" if action == "up" else "Bring down"
        if st.button(f"{'Hide' if is_open else 'Show'} {label_verb} Output for {name}", key=f"btn_make_logs_{name}"):
            _toggle_panel(log_state_key)
            st.rerun(scope="fragment")
        if st.session_state.get(log_state_key, False):
            st.text_area(
                f"make {action} output: {name}",
                get_make_job_logs(cid),
                height=300,
                key=f"make_logs_area_{name}",
                disabled=True
            )

    if containers:
        with st.expander(f"Containers ({len(containers)})", expanded=False):
            if len(containers) > 1:
                render_group_logs_panel(name, containers)
            for c in containers:
                render_container_row(c['id'], c['name'], c['image'])
    st.divider()


@st.fragment
def render_group_logs_panel(group_name, group_containers):
    # Fragment-scoped: toggling combined logs only reruns this panel, not the whole page.
    state_key = f"show_group_logs_{group_name}"
    is_open = st.session_state.get(state_key, False)
    label = f"{'Hide' if is_open else 'Show'} Combined Logs for {group_name} ({len(group_containers)} containers)"
    if st.button(label, key=f"btn_{state_key}"):
        _toggle_panel(state_key)
        st.rerun(scope="fragment")

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
        _toggle_panel(log_state_key)
        st.rerun(scope="fragment")

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