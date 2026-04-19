import re
from pathlib import Path

CONTROLLERS_DIR = Path("web/controllers")

# domain -> specific fixes
for fp in sorted(CONTROLLERS_DIR.glob("*.py")):
    if fp.name == "__init__.py":
        continue
    domain = fp.stem
    text = fp.read_text(encoding="utf-8")
    original = text

    # 1. rename bp -> {domain}_bp
    old_bp = f'{domain}_bp = Blueprint("{domain}"'
    if 'bp = Blueprint("' in text and old_bp not in text:
        text = text.replace('bp = Blueprint(', f'{domain}_bp = Blueprint(')
        text = re.sub(r'@bp\.route', f'@{domain}_bp.route', text)

    # 2. specific self fixes per file
    if domain == "system":
        text = text.replace("self._update_config(", "_update_config(")
        text = text.replace("self._set_system_config(", "_set_system_config(")
    elif domain == "media":
        text = text.replace("self._media_similar(", "_media_similar(")
        text = text.replace("self._media_recommendations(", "_media_recommendations(")
        text = text.replace("self._person_medias(", "_person_medias(")
        text = text.replace("self.get_downloaded(", "get_downloaded(")
        text = text.replace("self.re_identification(", "re_identification(")
        # add import for re_identification if not present
        if "re_identification(" in text and "from web.controllers.sync import re_identification" not in text:
            # insert after existing imports, before first blank line after imports
            lines = text.splitlines()
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("from ") or line.startswith("import "):
                    insert_idx = i + 1
            lines.insert(insert_idx, "from web.controllers.sync import re_identification")
            text = "\n".join(lines)
    elif domain == "rss":
        text = text.replace("self.get_movie_rss_items(", "get_movie_rss_items(")
        text = text.replace("self._movie_calendar_data(", "_movie_calendar_data(")
        text = text.replace("self.get_tv_rss_items(", "get_tv_rss_items(")
        text = text.replace("self._tv_calendar_data(", "_tv_calendar_data(")
    elif domain == "sync":
        text = text.replace("self._manual_transfer(", "_manual_transfer(")
        # fix undefined command in _exec_test_command
        if "command.strip()" in text:
            text = text.replace('m = re.match(r"^(\\w+)\\(\\)\\.(\\w+)\\(\\)$", command.strip())',
                                'cmd = data.get("command", "") if isinstance(data, dict) else str(data)\n        m = re.match(r"^(\\w+)\\(\\)\\.(\\w+)\\(\\)$", cmd.strip())')
    elif domain == "brush":
        # Replace WebActionBrushMixin constants with inline copies
        if "WebActionBrushMixin._RSS_RULE_FIELDS" in text:
            # insert constants near top
            const_block = '''_RSS_RULE_FIELDS = {
    "free": "brushtask_free",
    "hr": "brushtask_hr",
    "size": "brushtask_torrent_size",
    "include": "brushtask_include",
    "exclude": "brushtask_exclude",
    "dlcount": "brushtask_dlcount",
    "peercount": "brushtask_peercount",
    "pubdate": "brushtask_pubdate",
    "upspeed": "brushtask_upspeed",
    "downspeed": "brushtask_downspeed",
    "exclude_subscribe": "brushtask_exclude_subscribe",
}
_REMOVE_RULE_FIELDS = {
    "mode": "brushtask_mode",
    "time": "brushtask_seedtime",
    "hr_time": "brushtask_hr_seedtime",
    "ratio": "brushtask_seedratio",
    "uploadsize": "brushtask_seedsize",
    "dltime": "brushtask_dltime",
    "avg_upspeed": "brushtask_avg_upspeed",
    "iatime": "brushtask_iatime",
    "pending_time": "brushtask_pending_time",
    "freespace": "brushtask_freespace",
    "freestatus": "brushtask_freestatus",
}
_STOP_RULE_FIELDS = {
    "stopfree": "brushtask_stopfree",
}

'''
            # place before blueprint definition
            text = text.replace(f'{domain}_bp = Blueprint("brush"', const_block + f'{domain}_bp = Blueprint("brush"')
            text = text.replace("WebActionBrushMixin._RSS_RULE_FIELDS", "_RSS_RULE_FIELDS")
            text = text.replace("WebActionBrushMixin._REMOVE_RULE_FIELDS", "_REMOVE_RULE_FIELDS")
            text = text.replace("WebActionBrushMixin._STOP_RULE_FIELDS", "_STOP_RULE_FIELDS")
    elif domain == "plugin":
        text = text.replace("def install_plugin(data):", "def install_plugin(data, reload=True):")
    elif domain == "scheduler":
        # rename local success shadowing
        text = re.sub(r'^(\s+)success = scheduler\.(remove_job|pause_job|resume_job)\(job_id\)',
                      r'\1ret = scheduler.\2(job_id)', text, flags=re.M)
        text = text.replace('if success:', 'if ret:')
        text = text.replace('return success(msg=', 'return success(msg=')  # no-op, just ensure
    elif domain == "rbac":
        # rename local success shadowing (pattern: success, result = ...)
        text = re.sub(r'^(\s+)success, result = ', r'\1ok, result = ', text, flags=re.M)
        text = text.replace('if success:', 'if ok:')
        text = text.replace('return success(success=True', 'return success(success=True')
        # the line above would break after replace? no, we replaced only the assignment.
        # But there are return statements like: return success(success=True, ...)
        # That uses the imported function, so it's fine.

    if text != original:
        fp.write_text(text, encoding="utf-8")
        print(f"[FIXED] {fp}")
    else:
        print(f"[OK] {fp}")
