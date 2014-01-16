#include <windows.h>
#include "olmem.h"
#include "olerrors.h"
#include "oldaapi.h"
#include "stdio.h"

extern "C" {
__declspec(dllexport) const char* __cdecl translateError(int code);
}

/* Much of the code in this file was copied verbatim from the
 * "ContDac" example in the Data Translation SDK.
 */

#define ERR_NO_BOARDS 123454321

#define ERRLEN 80
char errStr[ERRLEN];


#define CHECKERROR(ecode) if ((board.status = (ecode)) != OLNOERROR)\
                  {\
                  olDaReleaseDASS(board.hdass);\
                  olDaTerminate(board.hdrvr);\
                  return ((UINT)board.status);}

typedef struct tag_board {
   HDEV hdrvr;         /* device handle            */
   HDASS hdass;        /* sub system handle        */
   ECODE status;       /* board error status       */
   HBUF  hbuf;         /* sub system buffer handle */
   PWORD lpbuf;        /* buffer pointer           */
   char name[MAX_BOARD_NAME_LENGTH];  /* string for board name    */
   char entry[MAX_BOARD_NAME_LENGTH]; /* string for board name    */
} BOARD;

typedef BOARD* LPBOARD;

static BOARD board;


BOOL CALLBACK
GetDriver( LPSTR lpszName, 
           LPSTR lpszEntry, 
           LPARAM lParam )   
/*
this is a callback function of olDaEnumBoards, it gets the 
strings of the Open Layers board and attempts to initialize
the board.  If successful, enumeration is halted.
*/
{
   LPBOARD lpboard = (LPBOARD)(LPVOID)lParam;
   
   /* fill in board strings */

   lstrcpyn(lpboard->name,lpszName,MAX_BOARD_NAME_LENGTH);
   lstrcpyn(lpboard->entry,lpszEntry,MAX_BOARD_NAME_LENGTH);

   /* try to open board */

   lpboard->status = olDaInitialize(lpszName,&lpboard->hdrvr);
   printf("Loaded board named %s with entry %s and handle %d\n", lpboard->name, lpboard->entry, lpboard->hdrvr);
   if   (lpboard->hdrvr != NULL)
      return FALSE;          /* false to stop enumerating */
   else                      
      return TRUE;           /* true to continue          */
}


extern "C" {

__declspec(dllexport) int __cdecl initialize(void) {
   /* Get first available Open Layers board */
   
   board.hdrvr = NULL;
   CHECKERROR (olDaEnumBoards(GetDriver,(LPARAM)(LPBOARD)&board));

   /* check for error within callback function */

   CHECKERROR (board.status);

   /* check for NULL driver handle - means no boards */

   if (board.hdrvr == NULL){
      printf("No Open Layer boards!\n");
      return ((UINT)NULL);
   }

   /* get handle to D/A sub system */

   CHECKERROR (olDaGetDASS(board.hdrvr,OLSS_DA,0,&board.hdass));

   /* set subsystem for single value operation */

   CHECKERROR (olDaSetDataFlow(board.hdass,OL_DF_SINGLEVALUE));
   CHECKERROR (olDaConfig(board.hdass));
   return ((UINT)NULL);
}

__declspec(dllexport) int __cdecl setVoltage(UINT channel, float volts) {
   DBL min, max;
   UINT encoding, resolution;
   long value;
   DBL gain = 1.0;
   
   /* get sub system information for code/volts conversion */

   CHECKERROR (olDaGetRange(board.hdass,&max,&min));
   CHECKERROR (olDaGetEncoding(board.hdass,&encoding));
   CHECKERROR (olDaGetResolution(board.hdass,&resolution));

   value = (long) ((1L<<resolution)/((float)max-(float)min) * (volts - (float)min));
   value = min((1L<<resolution)-1,value);

   if (encoding != OL_ENC_BINARY) {
       // convert to 2's comp by inverting the sign bit
       long sign = 1L << (resolution - 1);
       value ^= sign;
       if (value & sign)           //sign extend
           value |= 0xffffffffL << resolution;
   }
   
   /* put single value */
   CHECKERROR (olDaPutSingleValue(board.hdass,value,channel,gain));

   /* display value with message box */

   return ((UINT)NULL);
}

__declspec(dllexport) int __cdecl cleanup(void) {
   /* release the subsystem and the board */

   CHECKERROR (olDaReleaseDASS(board.hdass));
   CHECKERROR (olDaTerminate(board.hdrvr));

   /* all done - return */
   return ((UINT)NULL);
}


__declspec(dllexport) const char* __cdecl translateError(int code) {
    olDaGetErrorString(code, errStr, ERRLEN);
    return errStr;
}

}
