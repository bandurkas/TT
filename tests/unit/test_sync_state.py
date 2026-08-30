from src.integrations.sync_state import JsonFileSyncStateStore, SyncState, SyncStateStore


def test_get_creates_idle_row_once():
    st = SyncStateStore()
    a = st.get("shop", "orders", "s1")
    assert a.status == "idle" and a.cursor is None
    assert st.get("shop", "orders", "s1") is a and len(st.all()) == 1


def test_lifecycle_and_idempotent_upsert():
    st = SyncStateStore()
    st.start_attempt("shop", "orders", "s1")
    assert st.get("shop", "orders", "s1").status == "running"
    st.mark_error("shop", "orders", "s1", "boom")
    e = st.get("shop", "orders", "s1")
    assert e.status == "error" and e.error == "boom" and e.last_successful_sync is None
    st.mark_success("shop", "orders", "s1", cursor="tok9")
    ok = st.get("shop", "orders", "s1")
    assert ok.status == "success" and ok.cursor == "tok9" and ok.error is None
    assert ok.last_successful_sync and ok.last_attempt
    st.upsert(ok)
    st.upsert(SyncState("shop", "orders", "s1", cursor="tok9", status="success"))
    assert len(st.all()) == 1 and st.get("shop", "orders", "s1").cursor == "tok9"


def test_json_file_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    st = JsonFileSyncStateStore(p)
    st.mark_success("ads", "report", "adv1", cursor="2026-08-29")
    st.mark_error("shop", "statements", "s1", "x" * 3000)
    st2 = JsonFileSyncStateStore(p)
    assert st2.get("ads", "report", "adv1").cursor == "2026-08-29"
    assert len(st2.get("shop", "statements", "s1").error) == 2000
    assert len(st2.all()) == 2
