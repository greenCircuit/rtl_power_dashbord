"""
Route package — imports all sub-modules so their @api_bp.route decorators
register against the single Blueprint defined in _helpers.py.
"""
from ._helpers import api_bp  # noqa: F401  (re-exported for app/__init__.py)

from . import status        # noqa: F401
from . import bands         # noqa: F401
from . import measurements  # noqa: F401
from . import analysis      # noqa: F401
