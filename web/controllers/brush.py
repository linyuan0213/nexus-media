from flask import Blueprint
from web.core.decorators import any_auth, parse_json_data
from web.core.response import success, fail
from app.services.brush_service import BrushService
from app.utils import ExceptionUtils

brush_bp = Blueprint("brush", __name__, url_prefix="/api/web/brush")


@brush_bp.route('/add_brushtask', methods=['POST'])
@any_auth
@parse_json_data
def _add_brushtask(data):
    """
    新增刷流任务
    """
    BrushService().add_or_update_task(data)
    return success()


@brush_bp.route('/brushtask_detail', methods=['POST'])
@any_auth
@parse_json_data
def _brushtask_detail(data):
    """
    查询刷流任务详情
    """
    dto = BrushService().get_task(data.get("id"))
    if not dto.task:
        return fail(task={})
    return success(task=dto.task)


@brush_bp.route('/list_brushtasks', methods=['POST'])
@any_auth
@parse_json_data
def _list_brushtasks(data):
    """
    查询所有刷流任务
    """
    return success(tasks=BrushService().get_tasks())


@brush_bp.route('/del_brushtask', methods=['POST'])
@any_auth
@parse_json_data
def _del_brushtask(data):
    """
    删除刷流任务
    """
    brush_id = data.get("id")
    if brush_id:
        BrushService().delete_task(brush_id)
        return success()
    return fail()


@brush_bp.route('/list_brushtask_torrents', methods=['POST'])
@any_auth
@parse_json_data
def _list_brushtask_torrents(data):
    """
    获取刷流任务的种子明细
    """
    dto = BrushService().get_torrents(data.get("id"))
    if not dto.torrents:
        return fail(msg="未下载种子或未获取到种子明细")
    return success(data=dto.torrents)


@brush_bp.route('/run_brushtask', methods=['POST'])
@any_auth
@parse_json_data
def _run_brushtask(data):
    BrushService().run_task(data.get("id"))
    return success()


@brush_bp.route('/update_brushtask_state', methods=['POST'])
@any_auth
@parse_json_data
def _update_brushtask_state(data):
    """
    批量暂停/开始刷流任务
    """
    try:
        BrushService().update_task_state(
            state=data.get("state"),
            task_ids=data.get("ids")
        )
        return success(msg="")
    except Exception as e:
        ExceptionUtils.exception_traceback(e)
        return fail(msg="刷流任务设置失败")
