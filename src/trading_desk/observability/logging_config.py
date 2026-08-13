from __future__ import annotations
import logging
import sys
from contextvars import ContextVar
import structlog

from config import Settings

class StructuredLog:
    _correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
  
    @staticmethod
    def set_correlation_id(correlation_id: str) -> None:
        StructuredLog._correlation_id_var.set(correlation_id)

    @staticmethod
    def _add_correlation_id(logger, method_name, event_dict):
        cid = StructuredLog._correlation_id_var.get()
        if cid:
            event_dict["correlation_id"] = cid
        return event_dict

    @staticmethod
    def configure_logging(settings: Settings)->None:
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=getattr(logging, settings.log_level.upper(), logging.INFO),
        )

        structlog.configure(
            processors = [
                structlog.contextvars.merge_contextvars,
                StructuredLog._add_correlation_id,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer()
            ],
            wrapper_class=structlog.make_filtering_bound_logger(   
                        getattr(logging, settings.log_level.upper(), logging.INFO)
                    ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True
        )

        if settings.langsmith_tracing:
                import os

                os.environ["LANGSMITH_TRACING"] = "true"
                if settings.langsmith_api_key:
                    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
                os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project

    @staticmethod
    def get_logger(name: str):
        return structlog.get_logger(name)