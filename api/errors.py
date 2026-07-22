"""Backend exception -> HTTP mapping. The API surfaces src/ refusals and
defects exactly as the backend states them — it never works around one."""

from __future__ import annotations

from contextlib import contextmanager

from fastapi import HTTPException

from src.config_loader import ConfigDefectError
from src.governance.review_queue import ResolutionError


@contextmanager
def backend_errors():
    from src.skills.meeting_summary import MeetingSummaryHalted
    from src.skills.scheduler import SchedulerError
    from src.skills.task_breakdown import TaskBreakdownHalted

    try:
        yield
    except ConfigDefectError as err:
        raise HTTPException(status_code=422, detail={"defects": err.defects}) from err
    except ResolutionError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except (TaskBreakdownHalted, MeetingSummaryHalted) as err:
        raise HTTPException(
            status_code=409,
            detail=f"halted and surfaced to the reviewer: {err}",
        ) from err
    except SchedulerError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
