from fastapi import APIRouter

from ...services import event_log

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/process/{workflow_uuid}")
def get_process_events(workflow_uuid: str):
    conn = event_log._get_conn()
    rows = conn.execute(
        "SELECT * FROM process_events WHERE workflow_uuid = ? ORDER BY timestamp",
        (workflow_uuid,),
    ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        results.append(item)
    return results
