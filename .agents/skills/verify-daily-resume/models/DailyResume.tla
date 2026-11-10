------------------------------ MODULE DailyResume ------------------------------
EXTENDS Naturals
VARIABLES phase, done, pending, checkpointWritten, restarted, starts, victories
vars == <<phase, done, pending, checkpointWritten, restarted, starts, victories>>
Init == /\ phase = "Home" /\ done = FALSE /\ checkpointWritten = FALSE
        /\ pending = FALSE /\ restarted = FALSE /\ starts = 0 /\ victories = 0
EnterBatch == /\ phase = "Home" /\ ~done /\ starts < 2 /\ phase' = "Formation"
              /\ pending' = TRUE
              /\ UNCHANGED <<done, checkpointWritten, restarted, starts, victories>>
StartBattle == /\ phase = "Formation" /\ phase' = "Fighting" /\ starts' = starts + 1
               /\ UNCHANGED <<done, pending, checkpointWritten, restarted, victories>>
BattleWon == /\ phase = "Fighting" /\ phase' = "Victory" /\ victories' = victories + 1
             /\ UNCHANGED <<done, pending, checkpointWritten, restarted, starts>>
RestartBeforeCheckpoint == /\ phase = "Victory" /\ ~restarted
                           /\ phase' = "RecoveringVictory" /\ restarted' = TRUE
                           /\ UNCHANGED <<done, pending, checkpointWritten, starts, victories>>
ObserveRecoveredSettlement == /\ phase = "RecoveringVictory" /\ phase' = "HomeSettlement"
                              /\ UNCHANGED <<done, pending, checkpointWritten, restarted, starts, victories>>
DismissRecoveredSettlement == /\ phase = "HomeSettlement" /\ phase' = "RecoveryCommitPending"
                              /\ UNCHANGED <<done, pending, checkpointWritten, restarted, starts, victories>>
RecordRecoveredCheckpoint == /\ phase = "RecoveryCommitPending" /\ pending /\ phase' = "ReturningHome"
                            /\ done' = TRUE /\ checkpointWritten' = TRUE /\ pending' = FALSE
                            /\ UNCHANGED <<restarted, starts, victories>>
ObserveHomeAfterRecovery == /\ phase = "ReturningHome" /\ phase' = "Home"
                           /\ UNCHANGED <<done, pending, checkpointWritten, restarted, starts, victories>>
ConfirmBattleSettlement == /\ phase = "Victory" /\ phase' = "CommitPending"
                           /\ UNCHANGED <<done, pending, checkpointWritten, restarted, starts, victories>>
RecordCheckpoint == /\ phase = "CommitPending" /\ phase' = "Checkpointed"
                    /\ done' = TRUE /\ checkpointWritten' = TRUE /\ pending' = FALSE
                    /\ UNCHANGED <<restarted, starts, victories>>
RestartAfterCheckpoint == /\ phase = "Checkpointed" /\ ~restarted
                          /\ phase' = "RecoveringDone" /\ restarted' = TRUE
                          /\ UNCHANGED <<done, pending, checkpointWritten, starts, victories>>
ReturnHome == /\ phase \in {"Checkpointed", "RecoveringDone"} /\ phase' = "Home"
              /\ UNCHANGED <<done, pending, checkpointWritten, restarted, starts, victories>>
Complete == /\ phase = "Home" /\ done /\ phase' = "Done"
            /\ UNCHANGED <<done, pending, checkpointWritten, restarted, starts, victories>>
Done == /\ phase = "Done" /\ UNCHANGED vars
Next == EnterBatch \/ StartBattle \/ BattleWon \/ RestartBeforeCheckpoint
        \/ ObserveRecoveredSettlement \/ DismissRecoveredSettlement \/ ObserveHomeAfterRecovery \/ ConfirmBattleSettlement
        \/ RecordRecoveredCheckpoint \/ RecordCheckpoint \/ RestartAfterCheckpoint \/ ReturnHome \/ Complete \/ Done
TypeOK == /\ phase \in {"Home", "Formation", "Fighting", "Victory", "RecoveringVictory", "HomeSettlement",
                        "RecoveryCommitPending", "ReturningHome", "CommitPending", "Checkpointed", "RecoveringDone", "Done"}
          /\ done \in BOOLEAN /\ pending \in BOOLEAN /\ checkpointWritten \in BOOLEAN /\ restarted \in BOOLEAN
          /\ starts \in 0..2 /\ victories \in 0..2
NoRepeatedBatch == starts <= 1
KeepCompletedCheckpoint == checkpointWritten => done
=============================================================================
