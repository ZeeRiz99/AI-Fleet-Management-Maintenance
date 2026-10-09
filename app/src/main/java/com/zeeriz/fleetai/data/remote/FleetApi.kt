package com.zeeriz.fleetai.data.remote

import com.zeeriz.fleetai.domain.model.Dashboard
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

    /** Re-runs the XGBoost model + SHAP on current data and returns the explained prediction. */
    @POST("api/v1/ai/predict/{id}")
    suspend fun predict(@Path("id") id: Int): Prediction

    /** Records a completed service; the backend re-scores the vehicle and returns before/after predictions. */
    @POST("api/v1/maintenance")
    suspend fun recordService(@Body body: ServiceRecordRequest): ServiceRecordResult
}
