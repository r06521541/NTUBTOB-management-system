package tw.org.ntubtob.portal

import android.app.Activity
import android.os.CancellationSignal
import androidx.credentials.CredentialManager
import androidx.credentials.CredentialManagerCallback
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.GetCredentialResponse
import androidx.credentials.exceptions.GetCredentialException
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.Executor

/** Explicit interactive proof only; never use a cached/silent credential fallback. */
class GoogleAuthorizationBridge(private val activity: Activity, messenger: BinaryMessenger) {
    private val channel = MethodChannel(messenger, "tw.org.ntubtob.portal/google_authorization")
    private var active: MethodChannel.Result? = null
    private var cancellation: CancellationSignal? = null
    private var disposed = false

    init {
        channel.setMethodCallHandler(::handle)
    }

    private fun handle(call: MethodCall, result: MethodChannel.Result) {
        if (call.method != "authorize") {
            result.notImplemented()
            return
        }
        if (disposed || active != null || activity.isFinishing || activity.isDestroyed) {
            reject(result)
            return
        }
        val args = call.arguments as? Map<*, *>
        val nonce = args?.get("raw_nonce") as? String
        val client = args?.get("client_id") as? String
        val server = args?.get("server_client_id") as? String
        val clientPattern = Regex("[0-9A-Za-z][0-9A-Za-z._-]{5,199}\\.apps\\.googleusercontent\\.com")
        if (args?.size != 3 || nonce == null || !Regex("[A-Za-z0-9_-]{43}").matches(nonce) ||
            client != "" || server == null || !clientPattern.matches(server)) {
            reject(result)
            return
        }
        active = result
        val signal = CancellationSignal()
        cancellation = signal
        try {
            val option = GetSignInWithGoogleOption.Builder(server).setNonce(nonce).build()
            val request = GetCredentialRequest.Builder().addCredentialOption(option).build()
            CredentialManager.create(activity).getCredentialAsync(
                activity, request, signal, Executor { activity.runOnUiThread(it) },
                object : CredentialManagerCallback<GetCredentialResponse, GetCredentialException> {
                    override fun onResult(response: GetCredentialResponse) {
                        if (active !== result) return
                        try {
                            val credential = response.credential
                            if (credential !is CustomCredential ||
                                credential.type != GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
                                complete(result, null)
                                return
                            }
                            val token = GoogleIdTokenCredential.createFrom(credential.data).idToken
                            complete(result, token.takeIf { it.isNotEmpty() && it.length <= 16_384 })
                        } catch (_: Exception) {
                            complete(result, null)
                        }
                    }

                    override fun onError(error: GetCredentialException) {
                        complete(result, null)
                    }
                },
            )
        } catch (_: Exception) {
            complete(result, null)
        }
    }

    private fun complete(expected: MethodChannel.Result, token: String?) {
        if (active !== expected) return
        active = null
        cancellation = null
        if (disposed || activity.isFinishing || activity.isDestroyed || token == null) {
            reject(expected)
        } else {
            expected.success(mapOf("identity_token" to token))
        }
    }

    fun dispose() {
        disposed = true
        channel.setMethodCallHandler(null)
        val pending = active
        active = null
        try {
            cancellation?.cancel()
        } catch (_: Exception) {
            // Disposal still completes only with the fixed failure below.
        }
        cancellation = null
        if (pending != null) reject(pending)
    }

    private fun reject(result: MethodChannel.Result) {
        result.error("google_authorization_unavailable", "Google authorization did not complete", null)
    }
}
