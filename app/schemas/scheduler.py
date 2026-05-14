"""
调度器相关 DTO
"""
from typing import Any

from pydantic import BaseModel, Field


class JobTrigger(BaseModel):
    type: str = "unknown"
    seconds: int | None = None
    expression: str | None = None
    run_date: str | None = None


class JobStatistics(BaseModel):
    total_runs: int = 0
    success_count: int = 0
    failure_count: int = 0


class SchedulerJob(BaseModel):
    id: str
    name: str
    next_run_time: str | None = None
    trigger: JobTrigger
    trigger_type: str = "unknown"
    args: list[str] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    jobstore: str = "default"
    paused: bool = False
    statistics: dict[str, Any] = Field(default_factory=dict)


class DeleteSchedulerJobRequest(BaseModel):
    id: str


class DeleteSchedulerJobResponse(BaseModel):
    code: int = 0
    msg: str = ""


class GetSchedulerJobsResponse(BaseModel):
    code: int = 0
    data: list[SchedulerJob] = Field(default_factory=list)


class PauseSchedulerJobRequest(BaseModel):
    id: str


class PauseSchedulerJobResponse(BaseModel):
    code: int = 0
    msg: str = ""


class ResumeSchedulerJobRequest(BaseModel):
    id: str


class ResumeSchedulerJobResponse(BaseModel):
    code: int = 0
    msg: str = ""


class RunSchedulerJobRequest(BaseModel):
    id: str


class RunSchedulerJobResponse(BaseModel):
    code: int = 0
    msg: str = ""


class UpdateSchedulerJobRequest(BaseModel):
    id: str
    trigger: str = Field(..., pattern="^(interval|cron|date)$")
    seconds: int | None = None
    minutes: int | None = None
    hours: int | None = None
    cron: str | None = None
    run_date: str | None = None


class UpdateSchedulerJobResponse(BaseModel):
    code: int = 0
    msg: str = ""
