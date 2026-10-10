package com.zeeriz.fleetai.data.remote

import com.zeeriz.fleetai.domain.model.Dashboard
import com.zeeriz.fleetai.domain.model.MaintenancePage
import com.zeeriz.fleetai.domain.model.MaintenanceSummary
import com.zeeriz.fleetai.domain.model.ScheduleItem
import com.zeeriz.fleetai.domain.model.Prediction
import com.zeeriz.fleetai.domain.model.ServiceRecordRequest
import com.zeeriz.fleetai.domain.model.ServiceRecordResult
import com.zeeriz.fleetai.domain.model.VehicleDetail
import com.zeeriz.fleetai.domain.model.VehicleSummary
import com.zeeriz.fleetai.domain.model.Health
import com.zeeriz.fleetai.domain.model.LoginRequest
import com.zeeriz.fleetai.domain.model.TokenResponse
import com.zeeriz.fleetai.domain.model.User
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/** REST endpoints of the FastAPI backend (api/main.py). */
interface FleetApi {
    @GET("api/v1/health")
    suspend fun health(): Health

    @POST("api/v1/auth/login")
    suspend fun login(@Body body: LoginRequest): TokenResponse

    @GET("api/v1/auth/me")
    suspend fun me(): User

    @GET("api/v1/dashboard")
    suspend fun dashboard(): Dashboard

    /** All vehicles; the app filters/sorts locally so the list also works offline. */
    @GET("api/v1/vehicles")
    suspend fun vehicles(): List<VehicleSummary>

    @GET("api/v1/vehicles/{id}")
    suspend fun vehicle(@Path("id") id: Int): VehicleDetail

    @GET("api/v1/maintenance/summary")
    suspend fun maintenanceSummary(): MaintenanceSummary

    /** status: overdue | due_soon | ok | unknown */
    @GET("api/v1/maintenance/schedule")
    suspend fun maintenanceSchedule(@Query("status") status: String, @Query("limit") limit: Int = 600): List<ScheduleItem>

    /** kind: Preventive | Breakdown | null for both; newest first */
    @GET("api/v1/maintenance/history")
    suspend fun maintenanceHistory(
        @Query("kind") kind: String? = null,
        @Query("limit") limit: Int = 50,
        @Query("offset") offset: Int = 0,
    ): MaintenancePage

    /** Re-runs the XGBoost model + SHAP on current data and returns the explained prediction. */
    @POST("api/v1/ai/predict/{id}")
    suspend fun predict(@Path("id") id: Int): Prediction

    /** Records a completed service; the backend re-scores the vehicle and returns before/after predictions. */
    @POST("api/v1/maintenance")
    suspend fun recordService(@Body body: ServiceRecordRequest): ServiceRecordResult
}
