package flwr.android_client

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.icu.text.SimpleDateFormat
import android.os.Bundle
import android.os.Environment
import android.os.IBinder
import android.os.PowerManager
import android.text.TextUtils
import android.text.method.ScrollingMovementMethod
import android.util.Log
import android.util.Patterns
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.room.Room
import dev.flower.flower_tflite.FlowerClient
import dev.flower.flower_tflite.FlowerServiceRunnable
import dev.flower.flower_tflite.LoggingService
import dev.flower.flower_tflite.SampleSpec
import dev.flower.flower_tflite.createFlowerService
import dev.flower.flower_tflite.helpers.classifierAccuracy
import dev.flower.flower_tflite.helpers.loadMappedFile
import dev.flower.flower_tflite.helpers.negativeLogLikelihoodLoss
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.io.IOException
import java.util.*
import kotlin.properties.Delegates
import kotlin.system.exitProcess


class MainActivity : AppCompatActivity() {
    private val scope = MainScope()
    lateinit var flowerClient: FlowerClient<Float3DArray, FloatArray>
    lateinit var flowerServiceRunnable: FlowerServiceRunnable<Float3DArray, FloatArray>
    private lateinit var loadDataButton: Button
    private lateinit var trainButton: Button
    private lateinit var resultText: TextView
    private lateinit var deviceId: EditText
    lateinit var db: Db

    private var wakeLock: PowerManager.WakeLock? = null

    private var CLIENT_ID by Delegates.notNull<Int>()
    private var MODEL_PATH by Delegates.notNull<String>()
    private var DATASET_PATH by Delegates.notNull<String>()
    private var LAYERS_SIZES by Delegates.notNull<IntArray>()
    private var CLASSES by Delegates.notNull<List<Any>>()
    private lateinit var SERVER_PORT: String
    private lateinit var SERVER_IP: String
    private var PARTITION_ID by Delegates.notNull<Int>()

    private var boundService: LoggingService? = null
    private var serviceBound = false

    private val serviceConnection = object : ServiceConnection {

        override fun onServiceConnected(name: ComponentName?, service: IBinder?) {

            val binder = service as LoggingService.MyBinder
            boundService = binder.getService()
            serviceBound = true
            Toast.makeText(this@MainActivity, "Service is connected", Toast.LENGTH_SHORT).show()

            CoroutineScope(Dispatchers.IO).launch {
                boundService!!.cleanLocalDB()
            }

            createFlowerClient {
                loadData {
                    startTrainig()
                }
            }
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            Toast.makeText(this@MainActivity, "Service is disconnected", Toast.LENGTH_SHORT).show()
            serviceBound = false
            boundService = null
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {

        super.onCreate(savedInstanceState)

        db = Room.databaseBuilder(this, Db::class.java, "model-db").build()
        setContentView(R.layout.activity_main)
        resultText = findViewById(R.id.grpc_response_text)
        resultText.movementMethod = ScrollingMovementMethod()
        deviceId = findViewById(R.id.device_id_edit_text)
        loadDataButton = findViewById(R.id.load_data)
        trainButton = findViewById(R.id.trainFederated)

        val json = readJSONFromFile()
        if (json != null) {
            CLIENT_ID = json.optInt("client_id")
            MODEL_PATH = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS).path + "/fl_testbed/" + json.optString("model")
            DATASET_PATH = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS).path + "/fl_testbed/" + json.optString("dataset")
            LAYERS_SIZES = json.optJSONArray("layers_sizes")?.let { jsonArrayToIntArray(it) }!!
            CLASSES = json.optJSONArray("classes")?.let { jsonArrayToList(it) }!!
            SERVER_PORT = json.optString("server_port")
            SERVER_IP = json.optString("server_ip")
            PARTITION_ID = json.optInt("partition_id")
        }
        else {
            CLIENT_ID = -1
        }

        // Acquire a wakelock
        val powerManager = getSystemService(POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(
            PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ON_AFTER_RELEASE,
            "YourApp:WakeLockTag"
        )
        wakeLock?.acquire()

        val serviceIntent = Intent(this, LoggingService::class.java)
        bindService(serviceIntent, serviceConnection, Context.BIND_AUTO_CREATE)
    }

    fun jsonArrayToList(jsonArray: JSONArray): List<String> {
        val list = mutableListOf<String>()

        for (i in 0 until jsonArray.length()) {
            list.add(jsonArray[i].toString())
        }

        return list
    }

    private fun jsonArrayToIntArray(jsonArray: JSONArray): IntArray {
        val intArray = IntArray(jsonArray.length())

        for (i in 0 until jsonArray.length()) {
            intArray[i] = jsonArray.getInt(i)
        }

        return intArray
    }

    private fun readJSONFromFile(): JSONObject? {
        var jsonObject: JSONObject? = null
        val file = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS), "fl_testbed/config.json")

        if (file.exists()) {
            try {
                val fileInputStream = FileInputStream(file)
                val size = fileInputStream.available()
                val buffer = ByteArray(size)
                fileInputStream.read(buffer)
                fileInputStream.close()

                val json = String(buffer, Charsets.UTF_8)
                jsonObject = JSONObject(json)
            } catch (e: IOException) {
                e.printStackTrace()
            }
        }
        return jsonObject
    }

    private fun createFlowerClient(callbacks: () -> Unit) {
        val buffer =  loadMappedFile(File(MODEL_PATH)) //loadMappedAssetFile(this, "model/cifar10.tflite") TODO
        val layersSizes = LAYERS_SIZES //intArrayOf(1800, 24, 9600, 64, 768000, 480, 40320, 336, 3360, 40) TODO
        val sampleSpec = SampleSpec<Float3DArray, FloatArray>(
            { it.toTypedArray() },
            { it.toTypedArray() },
            { Array(it) { FloatArray(CLASSES.size) } },
            ::negativeLogLikelihoodLoss,
            ::classifierAccuracy,
        )
        flowerClient = FlowerClient(buffer, layersSizes, sampleSpec, boundService)
        callbacks()
    }

    fun setResultText(text: String) {
        val dateFormat = SimpleDateFormat("HH:mm:ss", Locale.GERMANY)
        val time = dateFormat.format(Date())
        // resultText.append("\n$time   $text")
    }

    suspend fun runWithStacktrace(call: suspend () -> Unit) {
        try {
            call()
        } catch (err: Error) {
            Log.e(TAG, Log.getStackTraceString(err))
        }
    }

    suspend fun <T> runWithStacktraceOr(or: T, call: suspend () -> T): T {
        return try {
            call()
        } catch (err: Error) {
            Log.e(TAG, Log.getStackTraceString(err))
            or
        }
    }

    fun loadData(callbacks: () -> Unit) {
        scope.launch {
            loadDataInBackground()
            callbacks()
        }
    }

    suspend fun loadDataInBackground() {
        val result = runWithStacktraceOr("Failed to load training dataset.") {
            loadData(DATASET_PATH, flowerClient, PARTITION_ID, CLASSES)
            "Training dataset is loaded in memory. Ready to train!"
        }
    }

    fun startTrainig() {
        val host = SERVER_IP
        val portStr = SERVER_PORT
        if (TextUtils.isEmpty(host) || TextUtils.isEmpty(portStr) || !Patterns.IP_ADDRESS.matcher(
                host
            ).matches()
        ) {
            Toast.makeText(
                this,
                "Please enter the correct IP and port of the FL server",
                Toast.LENGTH_LONG
            ).show()
        } else {
            val port = if (TextUtils.isEmpty(portStr)) 0 else portStr.toInt()
            scope.launch {
                runWithStacktrace {
                    runGrpcInBackground(host, port)
                }
            }
            trainButton.isEnabled = false
            setResultText("Started training.")
        }
    }

    suspend fun runGrpcInBackground(host: String, port: Int) {
        val address = "dns:///$host:$port"
        val result = runWithStacktraceOr("Failed to connect to the FL server \n") {
            flowerServiceRunnable = createFlowerService(address, false, flowerClient) {
                if (it == "DONE"){
                    runBlocking {
                        CoroutineScope(Dispatchers.IO).launch {
                            flowerClient.loggingService?.transferDataToPostgresql(CLIENT_ID)
                            finishAndRemoveTask()
                            exitProcess(0)
                        }
                    }
                }

                Log.d(TAG, it)
            }
            "Connection to the FL server successful \n"
        }
        runOnUiThread {
            setResultText(result)
            trainButton.isEnabled = false
        }
    }

    fun hideKeyboard() {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        var view = currentFocus
        if (view == null) {
            view = View(this)
        }
        imm.hideSoftInputFromWindow(view.windowToken, 0)
    }

    override fun onDestroy() {
        super.onDestroy()
        if (serviceBound) {
            unbindService(serviceConnection)
            serviceBound = false
            boundService = null
        }
        // Release the wakelock
        wakeLock?.release()
        val devicePolicyManager = getSystemService(DEVICE_POLICY_SERVICE) as DevicePolicyManager
        devicePolicyManager.clearDeviceOwnerApp(this.packageName)
    }
}

private const val TAG = "MainActivity"

typealias Float3DArray = Array<Array<FloatArray>>
