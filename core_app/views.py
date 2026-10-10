import json
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.http import FileResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .evaluation import build_evaluation
from .analysis import summarize_results, validate_items
from .exports import export_history_to_xlsx, generate_docx_report
from .ml import get_available_rock_types, get_model_context, make_thumbnail, predict_properties
from .models import DetectionHistory


ROCK_TYPES = ["通用模型", "砂岩", "灰岩", "泥岩", "白云岩", "页岩"]


@login_required
def dashboard(request):
    return render(request, "core_app/dashboard.html", {"rock_types": get_available_rock_types() or ROCK_TYPES})


@login_required
def history_page(request):
    return render(request, "core_app/history.html")


def login_page(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    error = ""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("dashboard")
        error = "账号或密码错误"
    return render(request, "core_app/login.html", {"error": error})


def register_page(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    error = ""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        if not username or not password:
            error = "用户名和密码不能为空"
        elif User.objects.filter(username=username).exists():
            error = "用户已存在"
        else:
            form = UserCreationForm({"username": username, "password1": password, "password2": password})
            if form.is_valid():
                form.save()
                return redirect("login")
            error = "密码过短或过于简单，请换一个更安全的密码"
    return render(request, "core_app/register.html", {"error": error})


def logout_view(request):
    logout(request)
    return redirect("login")


@csrf_exempt
@require_POST
@login_required
def predict_image(request):
    rock_type = request.POST.get("rock_type") or "通用模型"
    files = request.FILES.getlist("images")
    available_rock_types = get_available_rock_types() or ROCK_TYPES
    if rock_type not in available_rock_types:
        return JsonResponse({"code": 400, "msg": "请选择有效岩石类型"}, status=400)
    if not files:
        return JsonResponse({"code": 400, "msg": "请上传岩心图像"}, status=400)

    results = []
    for image_file in files:
        image_bytes = image_file.read()
        porosity, permeability = predict_properties(image_bytes, rock_type)
        try:
            validate_items([{"porosity": porosity, "permeability": permeability}])
        except ValueError as exc:
            return JsonResponse({"code": 422, "msg": str(exc)}, status=422)
        DetectionHistory.objects.create(
            user=request.user,
            rock_type=rock_type,
            porosity=porosity,
            permeability=permeability,
            image=make_thumbnail(image_bytes),
        )
        results.append(
            {
                "section_index": len(results) + 1,
                "filename": image_file.name,
                "porosity": porosity,
                "permeability": permeability,
                "evaluation": build_evaluation(porosity, permeability),
            }
        )

    summary = summarize_results(results)
    return JsonResponse(
        {
            "code": 200,
            "msg": "识别完成",
            "data": {
                "rock_type": rock_type,
                "model_context": get_model_context(rock_type),
                "is_batch": len(results) > 1,
                "list": results,
                "summary": summary,
                "evaluation": build_evaluation(summary["avg_porosity"], summary["avg_permeability"]),
            },
        }
    )


@require_GET
@login_required
def history_api(request):
    records = DetectionHistory.objects.filter(user=request.user)
    data = [
        {
            "id": item.id,
            "rock_type": item.rock_type,
            "porosity": item.porosity,
            "permeability": item.permeability,
            "image": item.image,
            "created_at": item.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for item in records
    ]
    return JsonResponse({"code": 200, "data": data})


@csrf_exempt
@require_POST
@login_required
def delete_history(request):
    payload = json.loads(request.body or "{}")
    deleted, _ = DetectionHistory.objects.filter(user=request.user, id=payload.get("id")).delete()
    if not deleted:
        return JsonResponse({"code": 404, "msg": "记录不存在"}, status=404)
    return JsonResponse({"code": 200, "msg": "删除成功"})


@csrf_exempt
@require_POST
@login_required
def clear_history(request):
    DetectionHistory.objects.filter(user=request.user).delete()
    return JsonResponse({"code": 200, "msg": "清空成功"})


@csrf_exempt
@require_POST
@login_required
def export_docx(request):
    try:
        payload = json.loads(request.body or "{}")
        if not isinstance(payload, dict):
            raise ValueError("报告数据格式不正确。")
        items = validate_items(payload.get("list"))
        summary = summarize_results(items)
    except (ValueError, TypeError) as exc:
        return JsonResponse({"code": 400, "msg": str(exc)}, status=400)
    context = payload.get("model_context")
    is_demo = isinstance(context, dict) and context.get("is_demo") is True
    doc = generate_docx_report(request.user.username, payload.get("rock_type", "未选择"), items, summary, is_demo=is_demo)
    response = FileResponse(doc, as_attachment=True, filename="岩心储层评价报告.docx")
    response["Content-Type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return response


@csrf_exempt
@require_POST
@login_required
def export_history_xlsx(request):
    records = DetectionHistory.objects.filter(user=request.user)
    xlsx = export_history_to_xlsx(request.user.username, records)
    response = FileResponse(xlsx, as_attachment=True, filename="岩心历史记录.xlsx")
    response["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response
