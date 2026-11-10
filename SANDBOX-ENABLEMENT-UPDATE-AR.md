# تحديث بيئة التنفيذ — Railway Runner

تم استبدال الاعتماد السابق على Render Sandboxes بموصل داخلي لخدمة `alpha-runner` على Railway.

## البنية

- `alpha`: خدمة الويب وواجهة Alpha، ولا تنفذ كود المستخدم محلياً عندما يكون `ALPHA_RUNTIME_BACKEND=railway`.
- `alpha-runner`: خدمة Railway خاصة، تستقبل طلبات موقعة برمز `ALPHA_RUNNER_TOKEN` عبر Private Networking.
- يشغّل Runner مدير `RuntimeSandboxManager` الحالي، مع Linux user/mount/PID/network/IPC/UTS namespaces وchroot، ويُرفض التنفيذ إذا فشل فحص العزل.

## متغيرات الواجهة

- `ALPHA_RUNTIME_BACKEND=railway`
- `ALPHA_SANDBOX_ENABLED=1`
- `ALPHA_RUNNER_URL=http://alpha-runner.railway.internal:8080`
- `ALPHA_RUNNER_TOKEN=<shared secret>`

## متغيرات Runner

- `PORT=8080`
- `ALPHA_SANDBOX_ENABLED=1`
- `ALPHA_RUNNER_TOKEN=<same shared secret>`
- Dockerfile: `Dockerfile.runner`
- Healthcheck: `/internal/healthz`
- نسخة واحدة وGunicorn worker واحد.

لا توجد حاجة إلى `RENDER_API_KEY` أو `RENDER_WORKSPACE_ID` أو `RAILWAY_API_TOKEN`. لا تمرر مفاتيح قاعدة البيانات أو مفاتيح النماذج إلى Runner.

## شرط التفعيل الحقيقي

`ALPHA_SANDBOX_ENABLED=1` يطلب التفعيل فقط. يجب أن يظهر `/api/project-runtime/status` بقيم `provider=railway-runner`, `enabled=true`, `ready=true`, `missing=[]`. قد تمنع بيئة Railway user namespaces أو mount/chroot؛ عندئذٍ تبقى الميزة غير جاهزة ويُرفض تنفيذ الكود (fail-closed). لم يتم إجراء اختبار حي على حساب Railway من بيئة إعداد هذه الحزمة.
