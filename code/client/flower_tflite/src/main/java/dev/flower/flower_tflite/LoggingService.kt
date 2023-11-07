package dev.flower.flower_tflite

import android.app.ActivityManager
import android.app.Service
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Binder
import android.os.HardwarePropertiesManager
import android.os.IBinder
import android.os.StrictMode
import android.util.Log
import androidx.room.Room
import dev.flower.flower_tflite.database.Batch
import dev.flower.flower_tflite.database.BatchDao
import dev.flower.flower_tflite.database.Epoch
import dev.flower.flower_tflite.database.EpochDao
import dev.flower.flower_tflite.database.LoggingDB
import dev.flower.flower_tflite.database.Measurement
import dev.flower.flower_tflite.database.MeasurementDao
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import org.postgresql.util.PGobject
import java.io.File
import java.io.FileInputStream
import java.io.IOException
import java.sql.Connection
import java.sql.DriverManager
import java.sql.PreparedStatement
import java.sql.Timestamp
import java.text.SimpleDateFormat
import java.util.Properties
import kotlin.properties.Delegates


class LoggingService: Service() {

    // Binder for clients to communicate with the service.
    private val binder = MyBinder()
    private var measuring = false

    private lateinit var measurementDao: MeasurementDao
    private lateinit var epochDao: EpochDao
    private lateinit var batchDao: BatchDao

    private var epochID by Delegates.notNull<Long>()

    private lateinit var connection: Connection

    private lateinit var loggingDB: LoggingDB

    override fun onBind(intent: Intent?): IBinder? {
        Log.d(TAG, "Service bound")
        return binder
    }



    override fun onCreate() {

        super.onCreate()
        loggingDB = Room.databaseBuilder(applicationContext, LoggingDB::class.java, "logging_database").build()
        batchDao = loggingDB.batchDao()
        epochDao = loggingDB.epochDao()
        measurementDao = loggingDB.measurementDao()

        Log.d(TAG, "Service created")

        measuring = true
        Log.d(TAG, "Starting measurements on new thread: ${Thread.currentThread().id}")

        val scope = CoroutineScope(Dispatchers.IO)
        var cpuTimes: Array<Array<Long>>? = null

        // Perform your background tasks on a separate thread here.
        val workerThread = Thread {
            while (measuring) {

                // Get the device's CPU cores and frequency
                val hwManager =
                    getSystemService(HARDWARE_PROPERTIES_SERVICE) as HardwarePropertiesManager

                if (cpuTimes == null) {
                    cpuTimes = Array(hwManager.cpuUsages.size) { Array(2) { 0 } }
                    for ((count, i) in hwManager.cpuUsages.withIndex()) {
                        cpuTimes!![count][0] = i.active;
                        cpuTimes!![count][1] = i.total;
                    }
                }
                else {

                    var curCPUUsage = 0.0
                    val cpuJSON = JSONArray()

                    for ((count, i) in hwManager.cpuUsages.withIndex()) {

                        val curActive = i.active - cpuTimes!![count][0]
                        val curTotal = i.total - cpuTimes!![count][1]
                        val iCPUUsage = (curActive / curTotal.toDouble()) * 100
                        curCPUUsage += iCPUUsage
                        cpuTimes!![count][0] = i.active;
                        cpuTimes!![count][1] = i.total;

                        val file_cpu_all_freqs = File("/sys/devices/system/cpu/cpu$count/cpufreq/scaling_available_frequencies")
                        val file_cpu_all_governs = File("/sys/devices/system/cpu/cpu$count/cpufreq/scaling_available_governors")
                        val file_cpu_cur_freq = File("/sys/devices/system/cpu/cpu$count/cpufreq/scaling_cur_freq")
                        val file_cpu_cur_govern = File("/sys/devices/system/cpu/cpu$count/cpufreq/scaling_governor")
                        val file_cpu_max_freq = File("/sys/devices/system/cpu/cpu$count/cpufreq/scaling_max_freq")
                        val file_cpu_min_freq = File("/sys/devices/system/cpu/cpu$count/cpufreq/scaling_min_freq")

                        val cpu_all_freqs = readResourceFile(file_cpu_all_freqs)
                        val cpu_all_governs = readResourceFile(file_cpu_all_governs)
                        val cpu_cur_freq = readResourceFile(file_cpu_cur_freq)?.toInt()
                        val cpu_cur_govern = readResourceFile(file_cpu_cur_govern)
                        val cpu_max_freq = readResourceFile(file_cpu_max_freq)?.toInt()
                        val gpu_min_freq  = readResourceFile(file_cpu_min_freq)?.toInt()

                        val curCPUJson = JSONObject()
                        curCPUJson.put("cpu", count)
                        curCPUJson.put("usage", iCPUUsage)
                        curCPUJson.put("cpu_all_freqs", cpu_all_freqs?:"")
                        curCPUJson.put("cpu_all_governs", cpu_all_governs?:"")
                        curCPUJson.put("cpu_cur_freq", cpu_cur_freq?:0)
                        curCPUJson.put("cpu_cur_govern", cpu_cur_govern?:"")
                        curCPUJson.put("cpu_max_freq", cpu_max_freq?:0)
                        curCPUJson.put("cpu_min_freq", gpu_min_freq?:0)

                        cpuJSON.put(curCPUJson)

                    }

                    val file_gpu_util = File("/sys/kernel/gpu/gpu_busy")
                    val file_gpu_cur_clock = File("/sys/kernel/gpu/gpu_clock")
                    val file_gpu_govern = File("/sys/kernel/gpu/gpu_governor")
                    val file_gpu_freq_tab = File("/sys/kernel/gpu/gpu_freq_table")
                    val file_gpu_max_clock = File("/sys/kernel/gpu/gpu_max_clock")
                    val file_gpu_min_clock = File("/sys/kernel/gpu/gpu_min_clock")

                    val gpu_busy = readResourceFile(file_gpu_util)?.split("%")?.get(0)?.toDouble()
                    val gpu_cur_clock = readResourceFile(file_gpu_cur_clock)?.toInt()
                    val gpu_govern = readResourceFile(file_gpu_govern)
                    val gpu_freq_tab = readResourceFile(file_gpu_freq_tab)
                    val gpu_max_clock = readResourceFile(file_gpu_max_clock)?.toInt()
                    val gpu_min_clock  = readResourceFile(file_gpu_min_clock)?.toInt()

                    val gpuJSON = JSONObject()
                    gpuJSON.put("gpu_busy", gpu_busy?:0.0)
                    gpuJSON.put("gpu_cur_clock", gpu_cur_clock?:0)
                    gpuJSON.put("gpu_govern", gpu_govern?:"")
                    gpuJSON.put("gpu_freq_tab", gpu_freq_tab?:"")
                    gpuJSON.put("gpu_max_clock", gpu_max_clock?:0)
                    gpuJSON.put("gpu_min_clock", gpu_min_clock?:0)

                    val mi = ActivityManager.MemoryInfo()
                    val activityManager = getSystemService(ACTIVITY_SERVICE) as ActivityManager
                    activityManager.getMemoryInfo(mi)
                    val percentAvail: Double = (1 - (mi.availMem / mi.totalMem.toDouble())) * 100.0

                    val batteryStatus: Intent? =
                        IntentFilter(Intent.ACTION_BATTERY_CHANGED).let { ifilter ->
                            this.registerReceiver(null, ifilter)
                        }

                    val batteryPct: Float? = batteryStatus?.let { intent ->
                        val level: Int = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
                        val scale: Int = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
                        (level * 100).toFloat() / scale.toFloat()
                    }

                    if (batteryPct != null) {
                        scope.launch {
                            measurementDao.insertMeasurement(
                                Measurement(
                                    time = Timestamp(System.currentTimeMillis()).toString(),
                                    cpu_util = curCPUUsage,
                                    mem_util = percentAvail,
                                    gpu_util = gpu_busy?:0.0,
                                    battery_state = batteryPct,
                                    power_consumption = 0.0,
                                    gpuInfo = gpuJSON.toString(),
                                    cpuInfo = cpuJSON.toString()
                                )
                            )
                        }
                    }
                }
                Thread.sleep(100)
            }
        }

        // Start the worker thread.
        workerThread.start()
    }

    fun readResourceFile(file: File): String? {
        try {
            val inputStream: FileInputStream
            val byteArray: ByteArray
            if (file.exists() && file.canRead()) {
                inputStream = FileInputStream(file)
                byteArray = ByteArray(file.length().toInt())
                inputStream.read(byteArray)
                inputStream.close()
                return String(byteArray, Charsets.UTF_8).substringBefore("\n").trim()
            }
            else {
                Log.d(TAG,"GPU files not accessible")
            }
            // Now, 'byteArray' contains the binary data
        } catch (e: IOException) {
            Log.d(TAG,"GPU files not accessible")
        }
        return null
    }

    fun startEpoch(startTime: Timestamp, epochNumber: Int, cirID: Int){
        CoroutineScope(Dispatchers.IO).launch {
            epochID = epochDao.insertEpoch(Epoch(
                start_time = startTime.toString(),
                end_time = startTime.toString(),
                epoch_number = epochNumber,
                cir_id = cirID
            ))[0]
        }
    }

    fun writeBatch(
        startTime: Timestamp, endTime: Timestamp, loss: Float, batchNumber: Int,
        frwdPassTime: Timestamp, bkwdPass: Timestamp, optStep: Timestamp){

        CoroutineScope(Dispatchers.IO).launch {
            batchDao.insertBatch(Batch(
                epoch_id = epochID,
                start_time = startTime.toString(),
                end_time = endTime.toString(),
                loss = loss,
                batch_number = batchNumber,
                frwd_pass_time = frwdPassTime.toString(),
                bkwd_pass_time = bkwdPass.toString(),
                opt_step_time = optStep.toString()
            ))
        }

    }

    fun endEpoch(endTime: Timestamp){
        CoroutineScope(Dispatchers.IO).launch {
            val insertedEpoch = epochDao.get(epochID)
            if (insertedEpoch != null) {
                epochDao.updateEpoch(endTime.toString(), insertedEpoch.id)
            }
        }
    }

    suspend fun transferDataToPostgresql(CLIENT_ID: Int) {

        val policy = StrictMode.ThreadPolicy.Builder().permitAll().build()
        StrictMode.setThreadPolicy(policy)

        Class.forName("org.postgresql.Driver");
        val jdbcUrl = "jdbc:postgresql://10.0.0.100:5432/fl_testbed_db"
        val connectionProps = Properties()
        connectionProps["user"] = "fl_testbed_admin"
        connectionProps["password"] = "fl_testbed_admin"
        connectionProps.setProperty("ssl","false");

        val connection = DriverManager.getConnection(jdbcUrl, connectionProps)
        val format = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS")

        // SQL insert statement
        val insertQueryEpochs = """
        INSERT INTO fl_testbed_logging.epochs (epoch_number, start_time, end_time, cir_id)
        VALUES (?, ?, ?, ?) RETURNING epoch_id
        """

        val epochs = epochDao.get()
        for (i in epochs){
            // INSERT EPOCH
            val preparedStatementEpochs: PreparedStatement = connection.prepareStatement(insertQueryEpochs)
            val start_time = format.parse(i.start_time)?.time
            val end_time = format.parse(i.end_time)?.time
            preparedStatementEpochs.setInt(1, i.epoch_number);
            preparedStatementEpochs.setTimestamp(2, start_time?.let { Timestamp(it) });
            preparedStatementEpochs.setTimestamp(3, end_time?.let { Timestamp(it) });
            preparedStatementEpochs.setInt(4, i.cir_id);
            // Execute the query to insert an epoch
            val epochResultSet = preparedStatementEpochs.executeQuery()
            if (epochResultSet.next()) {
                val id = epochResultSet.getInt(1) // Get the inserted epoch ID
                // SQL insert statement
                val insertQueryBatches = """
                    INSERT INTO fl_testbed_logging.batches (batch_number, start_time, end_time, loss, frwd_pass_time, bkwd_pass_time, opt_step_time, epoch_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                val preparedStatementBatches: PreparedStatement = connection.prepareStatement(insertQueryBatches)
                val batches = batchDao.get(i.id)
                for (j in batches){
                    val start_time_batch = format.parse(j.start_time)?.time
                    val end_time_batch = format.parse(j.end_time)?.time
                    val frwd_pass_time = format.parse(j.frwd_pass_time)?.time
                    val bkwd_pass_time = format.parse(j.bkwd_pass_time)?.time
                    val opt_step_time = format.parse(j.opt_step_time)?.time
                    preparedStatementBatches.setInt(1, j.batch_number);
                    preparedStatementBatches.setTimestamp(2, start_time_batch?.let { Timestamp(it) });
                    preparedStatementBatches.setTimestamp(3, end_time_batch?.let { Timestamp(it) });
                    preparedStatementBatches.setFloat(4, j.loss);
                    preparedStatementBatches.setTimestamp(5, frwd_pass_time?.let { Timestamp(it) });
                    preparedStatementBatches.setTimestamp(6, bkwd_pass_time?.let { Timestamp(it) });
                    preparedStatementBatches.setTimestamp(7, opt_step_time?.let { Timestamp(it) });
                    preparedStatementBatches.setInt(8, id);
                    preparedStatementBatches.addBatch();
                }
                preparedStatementBatches.executeBatch()
                preparedStatementBatches.close()
            }
            preparedStatementEpochs.close()
        }

        // INSERT MEASURES
        val insertQueryMeasurements = """
        INSERT INTO fl_testbed_logging.device_measurements (time, cpu_util, mem_util, gpu_util, battery_state, power_consumption, client_id, cpu_info, gpu_info)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        // Create a prepared statement
        val preparedStatementMeasurements: PreparedStatement = connection.prepareStatement(insertQueryMeasurements)

        val measurements = measurementDao.get()
        for (i in measurements){
            val date = format.parse(i.time)
            val timestamp = date?.time
            preparedStatementMeasurements.setTimestamp(1, timestamp?.let { Timestamp(it) });
            preparedStatementMeasurements.setDouble(2, i.cpu_util);
            preparedStatementMeasurements.setDouble(3, i.mem_util);
            preparedStatementMeasurements.setDouble(4, i.gpu_util);
            preparedStatementMeasurements.setFloat(5, i.battery_state!!);
            preparedStatementMeasurements.setDouble(6, i.power_consumption);
            preparedStatementMeasurements.setInt(7, CLIENT_ID);

            val cpuJson = PGobject()
            cpuJson.type = "json"
            cpuJson.value = i.cpuInfo
            preparedStatementMeasurements.setObject(8, cpuJson)
            // preparedStatementMeasurements.setString(8, i.cpuInfo);

            val gpuJson = PGobject()
            gpuJson.type = "json"
            gpuJson.value = i.gpuInfo
            preparedStatementMeasurements.setObject(9, gpuJson)
            //preparedStatementMeasurements.setString(9, i.gpuInfo);

            preparedStatementMeasurements.addBatch();
        }

        // Execute the insert statement
        preparedStatementMeasurements.executeBatch()
        // Close the prepared statement and the database connection
        preparedStatementMeasurements.close()

        connection.close()

        // cleanLocalDB()
    }

    suspend fun cleanLocalDB(){
        measurementDao.delete()
        batchDao.delete()
        epochDao.delete()
    }

    override fun onDestroy() {
        super.onDestroy()
        measuring = false
        Log.d(TAG, "Service destroyed")
    }

    inner class MyBinder : Binder() {
        fun getService(): LoggingService {
            return this@LoggingService
        }
    }

    companion object {
        private const val TAG = "LoggingService"
    }
}