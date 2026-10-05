"""每个页面渲染前，自动往里塞点东西"""

from .permissions import can_view_dashboard

def dashboard_access(request):
    """把"能不能看大屏"塞给所有模板"""
    return {"can_view_dashboard": can_view_dashboard(request.user)}

