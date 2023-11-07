package flwr.android_client

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import dev.flower.flower_tflite.FlowerClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.File
import java.io.FileInputStream
import java.io.InputStreamReader
import java.util.concurrent.ExecutionException
import kotlin.properties.Delegates

suspend fun readPartitionFileLines(
    fileName: String,
    call: suspend (Int, String) -> Unit
) {
    withContext(Dispatchers.IO) {
        BufferedReader(InputStreamReader(FileInputStream(File(fileName)))).useLines {
            it.forEachIndexed { i, l -> launch { call(i, l) } }
        }
    }
}

/**
 * Load training data from disk.
 */
@Throws
suspend fun loadData(
    dataset_path: String,
    flowerClient: FlowerClient<Float3DArray, FloatArray>,
    device_id: Int,
    classes: List<Any>
) {
    CLASSES = classes as List<String>
    readPartitionFileLines("$dataset_path/partition_${  device_id - 1}_train.txt") { index, line ->
        if (index % 500 == 499) {
            Log.i(TAG, index.toString() + "th training image loaded")
        }
        addSample(flowerClient, "$dataset_path/$line", true)
    }
    readPartitionFileLines("$dataset_path/partition_${device_id - 1}_test.txt") { index, line ->
        if (index % 500 == 499) {
            Log.i(TAG, index.toString() + "th test image loaded")
        }
        addSample(flowerClient, "$dataset_path/$line", false)
    }
}

@Throws
private fun addSample(
    flowerClient: FlowerClient<Float3DArray, FloatArray>,
    photoPath: String,
    isTraining: Boolean
) {
    val options = BitmapFactory.Options()
    options.inPreferredConfig = Bitmap.Config.ARGB_8888
    val bitmap = BitmapFactory.decodeStream(FileInputStream(File(photoPath)), null, options)!!
    val sampleClass = getClass(photoPath)

    // get rgb equivalent and class
    val rgbImage = prepareImage(bitmap)

    // add to the list.
    try {
        flowerClient.addSample(rgbImage, classToLabel(sampleClass), isTraining)
    } catch (e: ExecutionException) {
        throw RuntimeException("Failed to add sample to model", e.cause)
    } catch (e: InterruptedException) {
        // no-op
    }
}

fun getClass(path: String): String {
    return path.split("/".toRegex()).dropLastWhile { it.isEmpty() }.toTypedArray()[8]
}

/**
 * Normalizes a camera image to [0; 1], cropping it
 * to size expected by the model and adjusting for camera rotation.
 */
private fun prepareImage(bitmap: Bitmap): Float3DArray {
    val normalizedRgb = Array(IMAGE_SIZE) { Array(IMAGE_SIZE) { FloatArray(3) } }
    for (y in 0 until IMAGE_SIZE) {
        for (x in 0 until IMAGE_SIZE) {
            val rgb = bitmap.getPixel(x, y)
            val r = (rgb shr 16 and LOWER_BYTE_MASK) * (1 / 255.0f)
            val g = (rgb shr 8 and LOWER_BYTE_MASK) * (1 / 255.0f)
            val b = (rgb and LOWER_BYTE_MASK) * (1 / 255.0f)
            normalizedRgb[y][x][0] = r
            normalizedRgb[y][x][1] = g
            normalizedRgb[y][x][2] = b
        }
    }
    return normalizedRgb
}

private const val TAG = "Load Data"
const val LOWER_BYTE_MASK = 0xFF

/**
 * CIFAR10 image size. This cannot be changed as the TFLite model's input layer expects
 * a 32x32x3 input.
 */
const val IMAGE_SIZE = 32

var CLASSES by Delegates.notNull<List<String>>()

fun classToLabel(className: String): FloatArray {
    return CLASSES.map {
        if (className == it) 1f else 0f
    }.toFloatArray()
}
