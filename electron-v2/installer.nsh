!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "Win\COM.nsh"

; Load and save the existing shell link so arguments, custom icons, hotkeys,
; window state and shell properties survive an update. Never create missing links.
!macro customHeader
!ifndef BUILD_UNINSTALLER
Function ZhishiRepairShortcut
  Exch $0
  Push $1
  Push $2
  Push $3
  Push $4
  Push $5
  Push $6
  Push $7
  StrCpy $1 0
  StrCpy $2 0
  ${if} ${FileExists} "$0"
    !insertmacro ComHlpr_CreateInProcInstance ${CLSID_ShellLink} ${IID_IShellLink} r1 ".r7"
    ${if} $7 = 0
      ${IUnknown::QueryInterface} $1 '("${IID_IPersistFile}",.r2).r7'
      ${if} $7 = 0
        ${IPersistFile::Load} $2 '("$0",0).r7'
        ${if} $7 = 0
          ${IShellLink::GetPath} $1 '(.r3,${NSIS_MAX_STRLEN},0,4).r7'
          ${if} $7 = 0
          ${andIf} $3 == "$appExe"
          ${andIf} $0 == "$newStartMenuLink"
            StrCpy $launchLink "$0"
          ${endif}
          ${if} $7 = 0
          ${andIf} $3 != "$appExe"
            ${GetFileName} "$3" $4
            ; Do not repurpose a same-named shortcut to some other application.
            ${if} $4 == "${APP_EXECUTABLE_FILENAME}"
              ${IShellLink::SetPath} $1 '("$appExe").r7'
              ${if} $7 = 0
                ${GetParent} "$3" $4
                ${IShellLink::GetWorkingDirectory} $1 '(.r5,${NSIS_MAX_STRLEN}).r7'
                ${if} $7 = 0
                ${andIf} $5 == $4
                  ${IShellLink::SetWorkingDirectory} $1 '("$INSTDIR")'
                ${endif}
                ${IShellLink::GetIconLocation} $1 '(.r5,${NSIS_MAX_STRLEN},.r6).r7'
                ${if} $7 = 0
                ${andIf} $5 == $3
                  ${IShellLink::SetIconLocation} $1 '("$appExe",$6)'
                ${endif}
                ${IPersistFile::Save} $2 '("$0",1).r7'
                ${if} $7 = 0
                ${andIf} $0 == "$newStartMenuLink"
                  StrCpy $launchLink "$0"
                ${endif}
                ${if} $7 != 0
                  DetailPrint "Could not repair shortcut: $0 ($7)"
                ${endif}
              ${endif}
            ${endif}
          ${endif}
        ${endif}
      ${endif}
    ${endif}
  ${endif}
  !insertmacro ComHlpr_SafeRelease $2
  !insertmacro ComHlpr_SafeRelease $1
  Pop $7
  Pop $6
  Pop $5
  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
  ClearErrors
FunctionEnd
!endif
!macroend

!macro customInstall
  ; Only use a start-menu link after verifying its target or successfully saving
  ; the repaired target. This preserves custom launch arguments and window state.
  StrCpy $launchLink "$appExe"
  ${if} ${isUpdated}
    !ifndef DO_NOT_CREATE_START_MENU_SHORTCUT
      Push "$newStartMenuLink"
      Call ZhishiRepairShortcut
    !endif
    !ifndef DO_NOT_CREATE_DESKTOP_SHORTCUT
      Push "$newDesktopLink"
      Call ZhishiRepairShortcut
    !endif
  ${endif}
!macroend


