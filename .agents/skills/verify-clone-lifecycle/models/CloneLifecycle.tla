---------------------------- MODULE CloneLifecycle ----------------------------
EXTENDS Naturals
VARIABLES state, waiting, readyRef, readyDelivery, cancelDelivery, activeRuns, shutdownFinished
vars == <<state, waiting, readyRef, readyDelivery, cancelDelivery, activeRuns, shutdownFinished>>
Init == /\ state = "Idle" /\ waiting = FALSE /\ readyRef = FALSE
        /\ readyDelivery = FALSE /\ cancelDelivery = FALSE /\ activeRuns = 0 /\ shutdownFinished = FALSE
Start == /\ state = "Idle" /\ ~shutdownFinished
         /\ state' = "Connecting" /\ waiting' = TRUE /\ readyRef' = TRUE
         /\ UNCHANGED <<readyDelivery, cancelDelivery, activeRuns, shutdownFinished>>
RdpConnected == /\ state = "Connecting" /\ state' = "LaunchingWorker"
                /\ UNCHANGED <<waiting, readyRef, readyDelivery, cancelDelivery, activeRuns, shutdownFinished>>
WorkerReady == /\ state = "LaunchingWorker" /\ state' = "Ready"
               /\ readyRef' = FALSE /\ readyDelivery' = TRUE
               /\ UNCHANGED <<waiting, cancelDelivery, activeRuns, shutdownFinished>>
DeliverReady == /\ readyDelivery /\ readyDelivery' = FALSE /\ waiting' = FALSE
                /\ UNCHANGED <<state, readyRef, cancelDelivery, activeRuns, shutdownFinished>>
Run == /\ state = "Ready" /\ activeRuns < 2 /\ ~shutdownFinished
       /\ state' = "Running" /\ activeRuns' = activeRuns + 1
       /\ UNCHANGED <<waiting, readyRef, readyDelivery, cancelDelivery, shutdownFinished>>
RunResult == /\ state = "Running" /\ state' = "Ready" /\ activeRuns' = 0
             /\ UNCHANGED <<waiting, readyRef, readyDelivery, cancelDelivery, shutdownFinished>>
BeginShutdown == /\ state \in {"Connecting", "LaunchingWorker", "Ready", "Running"}
                 /\ state' = "Stopping"
                 /\ readyRef' = FALSE /\ cancelDelivery' = readyRef
                 /\ UNCHANGED <<waiting, readyDelivery, activeRuns, shutdownFinished>>
CancelStarting == /\ cancelDelivery /\ waiting' = FALSE /\ cancelDelivery' = FALSE
                  /\ UNCHANGED <<state, readyRef, readyDelivery, activeRuns, shutdownFinished>>
FinishShutdown == /\ state = "Stopping" /\ ~cancelDelivery /\ state' = "Idle"
                  /\ readyRef' = FALSE /\ activeRuns' = 0 /\ shutdownFinished' = TRUE
                  /\ UNCHANGED <<waiting, readyDelivery, cancelDelivery>>
Done == /\ state = "Idle" /\ shutdownFinished /\ UNCHANGED vars
Next == Start \/ RdpConnected \/ WorkerReady \/ DeliverReady \/ Run \/ RunResult
        \/ BeginShutdown \/ CancelStarting \/ FinishShutdown \/ Done
TypeOK == /\ state \in {"Idle", "Connecting", "LaunchingWorker", "Ready", "Running", "Stopping"}
          /\ waiting \in BOOLEAN /\ readyRef \in BOOLEAN /\ readyDelivery \in BOOLEAN /\ cancelDelivery \in BOOLEAN
          /\ activeRuns \in 0..2 /\ shutdownFinished \in BOOLEAN
NoOrphanStartWaiter == ~(shutdownFinished /\ waiting /\ ~readyDelivery)
SingleActiveRun == activeRuns <= 1
=============================================================================
