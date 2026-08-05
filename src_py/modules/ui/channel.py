import platform
from PyQt5.QtWebChannel import QWebChannel
from ..api import common

class API(QWebChannel):
    
    def __init__(self, parent=None):
        super().__init__(parent)

    from PyQt5.QtCore import pyqtSlot
    @pyqtSlot(str)
    def open_folder(self, folder_path: str):
        return common.open_folder(folder_path)
    @pyqtSlot()
    def get_service_config_list(self):
        return common.get_service_config_list()
    
    @pyqtSlot()
    def get_service_info_list(self):
        return common.get_service_info_list()

    # @pyqtSlot(str)
    # def start_live2d(self, service_name: str):
    #     return common.start_live2d(service_name)
