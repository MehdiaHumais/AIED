const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("aied", {
  pickFolder: () => ipcRenderer.invoke("folder:pick"),
  getUIState: () => ipcRenderer.invoke("ui:state"),
  notifyLogin: (token) => ipcRenderer.invoke("auth:login", token),
  notifyLogout: () => ipcRenderer.invoke("auth:logout"),
  onStatus: (cb) => {
    ipcRenderer.on("agent:status", (e, connected) => cb(connected));
  },
  onLog: (cb) => {
    ipcRenderer.on("agent:log", (e, msg) => cb(msg));
  },
});