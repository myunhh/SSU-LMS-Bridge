# backend/app/adapter/__init__.py
from .assignments import Assignment, list_all_deadlines, list_assignments
from .canvas_client import CanvasClient
from .courses import Course, list_courses
from .materials import Material, list_materials
from .notices import Notice, list_notices

__all__ = [
    "Assignment",
    "CanvasClient",
    "Course",
    "Material",
    "Notice",
    "list_all_deadlines",
    "list_assignments",
    "list_courses",
    "list_materials",
    "list_notices",
]
