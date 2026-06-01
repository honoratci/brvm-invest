@echo off
REM ═══════════════════════════════════════════════════════════════
REM  BRVM Auto Update — Installation tâche planifiée Windows
REM  Lance brvm_auto_update.py tous les jours à 18h30
REM  (après la clôture du marché BRVM à 15h30 heure locale)
REM ═══════════════════════════════════════════════════════════════

SET SCRIPT_DIR=%~dp0
SET PYTHON_EXE=python
SET SCRIPT=%SCRIPT_DIR%brvm_auto_update.py
SET TASK_NAME=BRVM_Auto_Update

echo.
echo  Installation de la tache planifiee Windows...
echo  Dossier : %SCRIPT_DIR%
echo  Script  : %SCRIPT%
echo.

REM Supprimer l'ancienne tâche si elle existe
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1

REM Créer la nouvelle tâche planifiée (tous les jours du lundi au vendredi à 18h30)
schtasks /Create ^
  /TN "%TASK_NAME%" ^
  /TR "\"%PYTHON_EXE%\" \"%SCRIPT%\"" ^
  /SC WEEKLY ^
  /D MON,TUE,WED,THU,FRI ^
  /ST 18:30 ^
  /F ^
  /RL HIGHEST ^
  /RU "%USERNAME%"

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo  [OK] Tache planifiee creee avec succes !
    echo  Nom     : %TASK_NAME%
    echo  Horaire : Lundi-Vendredi a 18h30
    echo.
    echo  Pour verifier : Gestionnaire de taches Windows
    echo  Pour lancer maintenant : schtasks /Run /TN "%TASK_NAME%"
) ELSE (
    echo.
    echo  [ERREUR] Echec creation tache. Verifiez les droits administrateur.
    echo  Essayez de lancer ce .bat en tant qu'Administrateur (clic droit).
)

echo.
pause
