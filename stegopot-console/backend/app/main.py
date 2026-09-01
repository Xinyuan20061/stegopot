"""StegoPot Console HTTP API。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.models import ExperimentView
from app.models import HealthResponse
from app.models import ImportResponse
from app.models import ReportListResponse
from app.models import ViewScope
from app.projector import ProjectionError
from app.projector import project_experiment
from app.projector import project_summary
from app.repository import InvalidReportError
from app.repository import ReportConflictError
from app.repository import ReportNotFoundError
from app.repository import ReportRepository
from app.repository import ReportRepositoryError


def create_app(settings: Settings | None = None) -> FastAPI:
  """创建可注入路径配置的 FastAPI 应用。

  参数：
    settings: 测试或部署时注入的配置；为空时读取环境变量。

  返回：
    已注册报告读取、导入和静态前端路由的 FastAPI 应用。
  """
  actual_settings = settings or Settings.from_environment()
  repository = ReportRepository(actual_settings.report_directory)
  application = FastAPI(
      title="StegoPot Console API",
      version="0.1.0",
      description="将 StegoPot 研究报告投影为稳定、脱敏的前端读取模型。",
  )
  application.state.repository = repository
  application.add_middleware(
      CORSMiddleware,
      allow_origins=list(actual_settings.allowed_origins),
      allow_credentials=False,
      allow_methods=["GET", "POST"],
      allow_headers=["Content-Type"],
  )

  @application.get("/api/health", response_model=HealthResponse)
  def health() -> HealthResponse:
    """返回 API 和报告目录的可用状态。"""
    return HealthResponse(report_count=repository.count())

  @application.get("/api/reports", response_model=ReportListResponse)
  def list_reports() -> ReportListResponse:
    """返回目录中全部合法实验报告摘要。"""
    summaries = []
    for report_id, document in repository.list_documents():
      try:
        summaries.append(project_summary(report_id, document))
      except ProjectionError:
        continue
    return ReportListResponse(reports=summaries, total=len(summaries))

  @application.get(
      "/api/reports/{report_id}",
      response_model=ExperimentView,
      response_model_exclude_none=True,
  )
  def get_report(
      report_id: str,
      scope: ViewScope = Query(default="public"),
  ) -> ExperimentView:
    """返回指定实验的公开或研究视图。"""
    try:
      return project_experiment(repository.load(report_id), scope=scope)
    except ReportNotFoundError as exc:
      raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InvalidReportError, ProjectionError) as exc:
      raise HTTPException(status_code=422, detail=str(exc)) from exc

  @application.post(
      "/api/reports",
      response_model=ImportResponse,
      status_code=status.HTTP_201_CREATED,
  )
  def import_report(
      document: dict[str, Any] = Body(...),
      overwrite: bool = Query(default=False),
  ) -> ImportResponse:
    """导入一份完整 StegoPot JSON 报告。"""
    try:
      project_experiment(document, scope="public")
      report_id = repository.save(document, overwrite=overwrite)
      return ImportResponse(id=report_id)
    except ReportConflictError as exc:
      raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (InvalidReportError, ProjectionError) as exc:
      raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ReportRepositoryError as exc:
      raise HTTPException(status_code=500, detail=str(exc)) from exc

  if actual_settings.frontend_dist.joinpath("index.html").is_file():
    application.mount(
        "/",
        StaticFiles(directory=actual_settings.frontend_dist, html=True),
        name="frontend",
    )
  return application


app = create_app()
