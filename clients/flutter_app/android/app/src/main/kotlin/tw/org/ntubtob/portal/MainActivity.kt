package tw.org.ntubtob.portal

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : FlutterActivity() {
    private var googleAuthorization: GoogleAuthorizationBridge? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        googleAuthorization = GoogleAuthorizationBridge(this, flutterEngine.dartExecutor.binaryMessenger)
    }

    override fun onDestroy() {
        googleAuthorization?.dispose()
        googleAuthorization = null
        super.onDestroy()
    }
}
