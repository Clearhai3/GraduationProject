"""用来允许用户来看的"""

def can_view_dashboard(user):
    """能不能看数据大屏"""
    if not user.is_authenticated:   # 没登录，一律不行
        return False
    if user.is_superuser:           # 防自锁: 管理员永远能看
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.can_view_dashboard)