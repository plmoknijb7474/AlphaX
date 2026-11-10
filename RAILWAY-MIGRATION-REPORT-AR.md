# تقرير نقل AlphaX من Render إلى Railway

## ما تغير

- استبدال موصل Render القديم بموصل `railway` يتصل بخدمة Runner خاصة عبر Railway Private Networking.
- إضافة `railway_runner.py` لتقديم API داخلية محمية برمز Bearer عشوائي.
- إضافة `Dockerfile` لخدمة الويب و`Dockerfile.runner` لخدمة التنفيذ.
- فصل متطلبات Runner في `requirements-runner.txt` وعدم تمرير أسرار التطبيق أو قاعدة البيانات إليها.
- حذف `render.yaml` و`render_sandbox_probe.py` واختبارات Render القديمة، وإزالة حزمة Render من متطلبات التشغيل.
- توثيق إنشاء خدمتي `alpha` و`alpha-runner` ومتغيراتهما في `DEPLOY-RAILWAY-SUPABASE-AR.md`.

## ما تم التحقق منه محلياً

- اجتاز `py_compile` الملفات الرئيسية: `app.py`, `runtime_sandbox.py`, `railway_runner.py`, `verify_alpha_deployment.py`.
- اجتازت اختبارات المشروع بعد تحديث اختبار إعداد النشر.
- اجتازت اختبارات Linux namespace/chroot المحلية المتاحة في بيئة الفحص.
- تم اختبار موصل Railway بمحاكاة HTTP للاتصال الخاص، والرمز، واستجابة الجاهزية.
- لم تعد `render>=...` من متطلبات التطبيق.

## حدود التحقق

- لم يتم النشر إلى حساب Railway الفعلي من جلسة التعديل، ولم تُستخدم بيانات دخول المستخدم.
- لم يتم بناء Docker images لأن Docker CLI/daemon غير متاح في بيئة الفحص الحالية.
- اختبارات API الخاصة بخدمة Runner تتطلب Flask؛ تم تخطيها في بيئة الفحص الحالية لعدم تثبيت Flask فيها. سيتم تثبيتها عند بناء صورة Runner من `requirements-runner.txt`.
- لم يتم التحقق من سماح Kernel/Container في Railway بصلاحيات `unshare`, user namespaces, mount وchroot. هذا شرط أساسي لعمل العزل. إذا فشل فحص الجاهزية، سترفض الخدمة تنفيذ الكود ولن تشغله داخل خدمة الويب.

## التحقق بعد النشر

يجب أن تظهر خدمة الويب `/healthz` بحالة HTTP 200، وخدمة Runner `/internal/healthz` بحالة HTTP 200. بعد تسجيل الدخول، يجب فحص `/api/project-runtime/status` والتأكد من `provider=railway-runner`, `enabled=true`, `ready=true`, و`missing=[]` قبل استخدام تنفيذ المشاريع.
