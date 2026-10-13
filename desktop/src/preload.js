/**
 * Renderer bridge: the window can query boot state and ask the shell to act.
 */
'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktop', {
  getState: () => ipcRenderer.invoke('get-state'),
  restartBackend: () => ipcRenderer.invoke('restart-backend'),
  openDashboard: () => ipcRenderer.invoke('open-dashboard'),
  chooseRepo: () => ipcRenderer.invoke('choose-repo'),
  onLog: (callback) => ipcRenderer.on('boot-log', (_event, lines) => callback(lines)),
  onStatus: (callback) => ipcRenderer.on('status', (_event, status) => callback(status)),
});
