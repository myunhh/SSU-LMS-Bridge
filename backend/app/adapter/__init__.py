# backend/app/adapter/__init__.py
from .canvas_client import CanvasClient
from .courses import Course, list_courses
from .assignments import Assignment, list_assignments, list_all_deadlines
from .notices import Notice, list_notices
from .materials import Material, list_materials
