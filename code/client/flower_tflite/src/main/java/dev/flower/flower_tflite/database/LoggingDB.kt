package dev.flower.flower_tflite.database

import androidx.room.*
import java.sql.Timestamp

@Database(entities = [Epoch::class, Batch::class, Measurement::class], version = 1, autoMigrations = [])
abstract class LoggingDB : RoomDatabase() {
    abstract fun measurementDao(): MeasurementDao
    abstract fun epochDao(): EpochDao
    abstract fun batchDao(): BatchDao
}

@Entity
data class Measurement(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val time: String,
    val cpu_util: Double,
    val mem_util: Double,
    val gpu_util: Double,
    val battery_state: Float?,
    val power_consumption: Double,
    val gpuInfo: String,
    val cpuInfo: String
)

@Entity
data class Epoch(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val start_time: String,
    val end_time: String,
    val epoch_number: Int,
    val cir_id: Int
)

@Entity
data class Batch(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val epoch_id: Long,
    val start_time: String,
    val end_time: String,
    val loss: Float,
    val batch_number: Int,
    val frwd_pass_time: String,
    val bkwd_pass_time: String,
    val opt_step_time: String
)

@Dao
interface MeasurementDao {
    @Query("SELECT * FROM Measurement")
    suspend fun get(): List<Measurement>

    @Query("DELETE FROM Measurement")
    suspend fun delete()

    @Insert
    suspend fun insertMeasurement(vararg measurement: Measurement)
}

@Dao
interface EpochDao {
    @Query("SELECT * FROM epoch WHERE id = :id")
    suspend fun get(id: Long): Epoch?

    @Query("DELETE FROM Epoch")
    suspend fun delete()

    @Query("SELECT * FROM epoch")
    suspend fun get(): List<Epoch>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertEpoch(vararg epoch: Epoch): List<Long>

    @Query("UPDATE epoch SET end_time = :cur_end_time WHERE id = :id")
    suspend fun updateEpoch(cur_end_time: String, id: Long)
}

@Dao
interface BatchDao {
    @Query("SELECT * FROM batch WHERE epoch_id = :epochId")
    suspend fun get(epochId: Long): List<Batch>

    @Query("DELETE FROM Batch")
    suspend fun delete()

    @Insert
    suspend fun insertBatch(vararg batch: Batch)
}
