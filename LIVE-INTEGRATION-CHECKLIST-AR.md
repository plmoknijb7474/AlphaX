# قائمة التحقق الحي — Railway + PostgreSQL + Alpha Runner

## قبل النشر

- [ ] رفع النسخة الحالية إلى المستودع `plmoknijb7474/AlphaX` والفرع `main`.
- [ ] إنشاء خدمة `alpha` من المستودع واستخدام `Dockerfile`.
- [ ] إنشاء خدمة `alpha-runner` من المستودع واستخدام `Dockerfile.runner` عبر `RAILWAY_DOCKERFILE_PATH`.
- [ ] وضع الخدمتين في المشروع والبيئة نفسيهما.
- [ ] عدم إنشاء Public Domain لخدمة Runner.
- [ ] ضبط `PORT=8080` وHealthcheck `/internal/healthz` لRunner.
- [ ] جعل Runner بنسخة واحدة وعامل Gunicorn واحد.
- [ ] إدخال متغيرات الويب حسب `DEPLOY-RAILWAY-SUPABASE-AR.md`.
- [ ] وضع `ALPHA_RUNNER_TOKEN` نفسه في الخدمتين (48 حرفاً أو أكثر).
- [ ] التأكد أن Runner لا يحتوي أسرار التطبيق أو قاعدة البيانات أو مفاتيح AI.

## اختبارات حية بعد النشر

1. `/healthz` على خدمة الويب يعيد HTTP 200.
2. `/internal/healthz` على خدمة Runner متاح عبر Private Networking فقط.
3. سجّل الدخول وافتح `/api/project-runtime/status`.
4. يجب أن يكون `provider=railway-runner`, `enabled=true`, `ready=true`, `missing=[]`.
5. أنشئ جلسة بملف ZIP تجريبي غير حساس بعد ظهور موافقة نقل الملفات.
6. جرّب تنفيذ `python main.py`.
7. تحقق من `exit_code`, stdout وstderr.
8. صدّر ZIP وتأكد من وجود الملف الناتج.
9. أوقف الجلسة وتأكد من إغلاقها.
10. جرّب طلب Runner دون Bearer token وتأكد من HTTP 401.

## إذا لم يكن Runner جاهزاً

راجع `note` و`probe_detail` في status وسجلات خدمة Runner. إذا أظهر فشل user namespaces أو mount أو chroot فهذا قيد صلاحيات في بيئة الاستضافة. لا تفعّل أي fallback لتشغيل كود المستخدم داخل خدمة الويب. لا ندّعي نجاح Sandbox قبل تجربة حية كاملة.
