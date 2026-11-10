# تحديث تفعيل Sandbox في Alpha — 9 نوفمبر 2026

تم تغيير الإعداد الافتراضي في `render.yaml` إلى:

```env
ALPHA_RUNTIME_BACKEND=render
ALPHA_SANDBOX_ENABLED=1
RENDER_SANDBOX_PLAN=1c-2g
```

## ماذا يعني التفعيل؟

- اختبارات `pytest` المعتادة تعمل في بيئة التطوير/CI، ولا تحتاج إلى تشغيلها داخل Sandbox المستخدم.
- عند بدء المستخدم جلسة Shell/Python من Project Intelligence، ينشئ Alpha بيئة Render Sandbox منفصلة ويشغّل الأوامر داخلها؛ لا ينفذ كود المستخدم داخل عملية Flask.
- تفعيل العلم وحده لا ينشئ Sandbox ولا يثبت أن حساب Render متصل. يلزم إدخال `RENDER_API_KEY` و`RENDER_WORKSPACE_ID` في Render Dashboard، وترك `RENDER_SANDBOX_GROUP_ID` اختيارياً للمجموعة الافتراضية.
- تحقق من `/api/project-runtime/status`: يجب أن تظهر `provider=render-sandboxes` و`enabled=true` و`missing=[]` و`ready=true`.
- لا يُستخدم تنفيذ محلي بديل داخل Flask إذا فشل الاتصال.

## حدود وخصوصية

- الملفات التي يختارها المستخدم تنتقل إلى Render Sandboxes في Oregon بعد موافقته الظاهرة. لا ترفع أسراراً أو مفاتيح أو ملفات حساسة.
- سياسة الخروج الشبكي `deny-all`. لا تُمرر `DATABASE_URL` أو مفاتيح Flask أو مفاتيح مزودي النماذج إلى Sandbox.
- الخطة الافتراضية `1c-2g`، مع مهلة تشغيل ساعة وتعليق بعد 20 دقيقة من الخمول وفق إعداد التطبيق.
- التفعيل لا ينشئ مورداً بذاته؛ بدء جلسة تنفيذ ينشئ Sandbox. تحاسب Render على موارد CPU والذاكرة أثناء النشاط، وعلى التخزين المؤقت للقطات وفق التسعير الحالي. راجع [Render Sandboxes](https://render.com/docs/sandboxes) و[التسعير](https://render.com/pricing).

## ما لم يتم التحقق منه هنا

تم تعديل ملفات المشروع فقط. لم تتوفر بيانات اعتماد Render في بيئة التعديل، لذلك لم يتم إنشاء Sandbox حية أو اختبار حساب المالك أو نشر Render.
