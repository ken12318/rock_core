from django.conf import settings
from django.db import models


class DetectionHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rock_type = models.CharField("岩石类型", max_length=20)
    porosity = models.FloatField("孔隙度")
    permeability = models.FloatField("渗透率")
    image = models.TextField("缩略图Base64")
    created_at = models.DateTimeField("检测时间", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "岩心检测记录"
        verbose_name_plural = "岩心检测记录"

    def __str__(self):
        return f"{self.user.username} - {self.rock_type} - {self.created_at:%Y-%m-%d %H:%M}"
