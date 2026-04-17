from .system import system_bp
from .media import media_bp
from .site import site_bp
from .download import download_bp
from .rss import rss_bp
from .userrss import userrss_bp
from .filter import filter_bp
from .words import words_bp
from .brush import brush_bp
from .sync import sync_bp
from .plugin import plugin_bp
from .rbac import rbac_bp
from .scheduler import scheduler_bp


def register_blueprints(app):
    bps = [
        system_bp, media_bp, site_bp, download_bp,
        rss_bp, userrss_bp, filter_bp, words_bp,
        brush_bp, sync_bp, plugin_bp, rbac_bp, scheduler_bp,
    ]
    for bp in bps:
        app.register_blueprint(bp)
