import glob
import logging
import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app import MainWindow


class ImportMixin:
    # Cross-DB import: read a second .db (legacy ANIKA, legacy BECKY, or unified MERCY)
    # into a fresh throwaway Database without touching the currently-open DB or the
    # source file.

    if TYPE_CHECKING:
        # Attribute provided by the composed FileManager (see file_manager/__init__.py).
        mainApp: MainWindow

    def importOtherDb(self, srcPath: str):
        # Read a second .db (legacy ANIKA, legacy BECKY, or unified MERCY) into a fresh
        # throwaway Database without touching the currently-open DB or the source file.
        # Returns (otherDb, fmt) on success or (None, "unknown" | "error") on failure.
        #
        # The source file is copied to a temp path first so any migration writes land on
        # the copy; the user's second .db is never mutated (§12.5(c)). The temp copy and
        # its WAL sidecars are cleaned up before returning.
        import tempfile
        from records import emptyDB
        # Deferred to avoid the circular `__init__.py imports ImportMixin` <-> `import_db
        # imports FileManager` bind at class-definition time.
        from file_manager import FileManager

        tmpFd, tmpPath = tempfile.mkstemp(suffix=".db")
        os.close(tmpFd)
        try:
            shutil.copy2(srcPath, tmpPath)
        except OSError as e:
            logging.error(f"Import error: could not copy {srcPath} to temp: {repr(e)}")
            try:
                os.unlink(tmpPath)
            except OSError:
                pass
            return None, "error"

        # Use a separate FileManager for the temp copy so its own backup-before-migration
        # logic runs against the copy, and any state on `self` is untouched.
        tmpFM = FileManager(self.mainApp)
        success = tmpFM.setFile(tmpPath)
        if not success:
            logging.error(f"Import error: unrecognized DB format in {srcPath}")
            _cleanupTempDb(tmpPath)
            return None, "unknown"

        otherDb = emptyDB()
        try:
            tmpFM._loadIntoDb(otherDb)
        finally:
            if tmpFM.dbFile is not None:
                tmpFM.dbFile.close()
            _cleanupTempDb(tmpPath)

        return otherDb, "ok"


def _cleanupTempDb(tmpPath: str):
    # Remove the temp DB file plus its WAL/SHM sidecars. Best-effort — a leftover temp
    # file is non-fatal, and Windows may hold the handle briefly after close().
    for suffix in ("", "-wal", "-shm"):
        p = tmpPath + suffix
        if os.path.exists(p):
            try:
                os.unlink(p)
            except OSError as e:
                logging.info(f"Import cleanup: could not remove {p}: {repr(e)}")
    # Also sweep any `.bak-*` sibling files the temp migration produced.
    for p in glob.glob(f"{tmpPath}.bak-*"):
        try:
            os.unlink(p)
        except OSError:
            pass
