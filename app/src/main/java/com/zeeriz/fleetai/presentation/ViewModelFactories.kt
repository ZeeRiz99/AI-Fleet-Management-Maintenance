package com.zeeriz.fleetai.presentation

import androidx.lifecycle.ViewModelProvider.AndroidViewModelFactory.Companion.APPLICATION_KEY
import androidx.lifecycle.viewmodel.CreationExtras
import com.zeeriz.fleetai.FleetApplication
import com.zeeriz.fleetai.di.AppContainer

/** Gives ViewModel factories access to the app's dependency container. */
val CreationExtras.container: AppContainer
    get() = (this[APPLICATION_KEY] as FleetApplication).container
