package edu.amrita.feedbackautomater.engine

import android.annotation.SuppressLint
import android.content.Context
import android.webkit.CookieManager
import android.webkit.JsResult
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject

/**
 * Coroutine-friendly wrapper around Android's built-in Chromium WebView.
 * Replaces Playwright on Android with zero external browser binaries.
 */
class WebViewController(context: Context) {

    private var pageFinishedDeferred: CompletableDeferred<Unit>? = null

    @SuppressLint("SetJavaScriptEnabled")
    val webView: WebView = WebView(context).apply {
        // Give headless WebView a real desktop viewport so visibility & layout checks work reliably
        layout(0, 0, 1280, 900)
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        // Desktop-like UA helps Outlook Web & Microsoft SSO render predictable DOM
        settings.userAgentString =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

        webChromeClient = object : WebChromeClient() {
            override fun onJsAlert(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
                result?.confirm()
                return true
            }

            override fun onJsConfirm(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
                result?.confirm()
                return true
            }
        }

        webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                pageFinishedDeferred?.complete(Unit)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                if (request?.isForMainFrame == true) {
                    pageFinishedDeferred?.complete(Unit)
                }
            }
        }
    }

    companion object {
        private const val JS_VISIBILITY_HELPER = """
            function __isVisible(el) {
                if (!el) return false;
                if (el.disabled) return false;
                if (el.getAttribute && el.getAttribute('aria-hidden') === 'true') return false;
                let cur = el;
                while (cur && cur.nodeType === 1) {
                    const st = window.getComputedStyle(cur);
                    if (!st || st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity) === 0) {
                        return false;
                    }
                    cur = cur.parentElement;
                }
                return true;
            }
            function __triggerClick(el) {
                if (el.focus) el.focus();
                el.click();
                try {
                    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                } catch (e) {}
            }
        """
    }

    suspend fun clearAllCookies() = withContext(Dispatchers.Main) {
        val cm = CookieManager.getInstance()
        val deferred = CompletableDeferred<Unit>()
        cm.removeAllCookies {
            cm.flush()
            deferred.complete(Unit)
        }
        deferred.await()
        webView.clearCache(true)
    }

    suspend fun loadUrl(url: String, timeoutMs: Long = 45_000L) = withContext(Dispatchers.Main) {
        val deferred = CompletableDeferred<Unit>()
        pageFinishedDeferred = deferred
        webView.loadUrl(url)
        withTimeoutOrNull(timeoutMs) { deferred.await() }
        delay(500)
    }

    suspend fun evalJs(script: String): String = withContext(Dispatchers.Main) {
        val deferred = CompletableDeferred<String>()
        webView.evaluateJavascript(script) { raw ->
            deferred.complete(decodeJsString(raw))
        }
        deferred.await()
    }

    private fun decodeJsString(raw: String?): String {
        if (raw == null || raw == "null") return ""
        return try {
            JSONObject("{\"v\":$raw}").getString("v")
        } catch (_: Exception) {
            raw.trim('"')
        }
    }

    suspend fun waitForSelector(cssSelector: String, timeoutMs: Long = 20_000L): Boolean {
        val escaped = JSONObject.quote(cssSelector)
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            val found = evalJs(
                """
                (function() {
                    $JS_VISIBILITY_HELPER
                    const els = Array.from(document.querySelectorAll($escaped));
                    return els.some(__isVisible) ? '1' : '0';
                })()
                """.trimIndent()
            )
            if (found == "1") return true
            delay(400)
        }
        return false
    }

    suspend fun fillInput(cssSelector: String, value: String): Boolean {
        val sel = JSONObject.quote(cssSelector)
        val valQuoted = JSONObject.quote(value)
        val res = evalJs(
            """
            (function() {
                $JS_VISIBILITY_HELPER
                const el = Array.from(document.querySelectorAll($sel)).find(__isVisible) || document.querySelector($sel);
                if (!el) return '0';
                el.focus();
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                if (setter) setter.call(el, $valQuoted); else el.value = $valQuoted;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                return '1';
            })()
            """.trimIndent()
        )
        return res == "1"
    }

    suspend fun clickSelector(cssSelector: String): Boolean {
        val sel = JSONObject.quote(cssSelector)
        val res = evalJs(
            """
            (function() {
                $JS_VISIBILITY_HELPER
                const el = Array.from(document.querySelectorAll($sel)).find(__isVisible);
                if (!el) return '0';
                __triggerClick(el);
                return '1';
            })()
            """.trimIndent()
        )
        return res == "1"
    }

    /**
     * Finds the deepest / most-specific visible element matching containsText
     * (never accidentally clicking an outer page wrapper div).
     */
    suspend fun clickElementByText(tagSelector: String, containsText: String): Boolean {
        val tag = JSONObject.quote(tagSelector)
        val txt = JSONObject.quote(containsText.trim().lowercase())
        val res = evalJs(
            """
            (function() {
                $JS_VISIBILITY_HELPER
                const needle = $txt;
                const candidates = Array.from(document.querySelectorAll($tag))
                    .filter(el => {
                        if (!__isVisible(el)) return false;
                        const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                        return t.includes(needle) && t.length <= needle.length + 80;
                    });
                if (candidates.length === 0) return '0';

                // Prefer interactive elements (a/button/role=button) and shortest text (deepest leaf)
                function score(el) {
                    const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                    const tagName = (el.tagName || '').toLowerCase();
                    const role = (el.getAttribute && (el.getAttribute('role') || '')).toLowerCase();
                    const isInteractive = (tagName === 'a' || tagName === 'button' || tagName === 'input' || role === 'button' || role === 'link');
                    return (isInteractive ? 0 : 1000) + t.length;
                }
                candidates.sort((a, b) => score(a) - score(b));

                let target = candidates[0];
                // If leaf is a span inside an anchor/button, click the clickable anchor/button
                const clickableAncestor = target.closest && target.closest("a, button, [role='button'], [role='link']");
                if (clickableAncestor && __isVisible(clickableAncestor)) {
                    target = clickableAncestor;
                }
                __triggerClick(target);
                return '1';
            })()
            """.trimIndent()
        )
        return res == "1"
    }

    suspend fun currentUrl(): String = withContext(Dispatchers.Main) {
        webView.url.orEmpty()
    }

    suspend fun destroy() = withContext(Dispatchers.Main) {
        webView.stopLoading()
        webView.destroy()
    }
}
