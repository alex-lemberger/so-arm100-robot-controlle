import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class UnityService {
  loadUnityGame(containerId: string) {
    const loaderScript = document.createElement('script');
    loaderScript.type = 'application/javascript';
    loaderScript.async = true;
    loaderScript.src = '/visualisations/droneSim/Build/droneSim.loader.js';

    loaderScript.addEventListener('load', () => {
      const config = {
        dataUrl: "/visualisations/droneSim/Build/droneSim.data.br",
        frameworkUrl: "/visualisations/droneSim/Build/droneSim.framework.js.br",
        codeUrl: "/visualisations/droneSim/Build/droneSim.wasm.br",
        streamingAssetsUrl: "StreamingAssets",
        companyName: "DefaultCompany",
        productName: "DroneSimulator",
        productVersion: "1.0",
        devicePixelRatio: 1,
        showBanner: false,
        backgroundColor: "#231F20",
        // Add loading progress callback
        onProgress: (_progress: number) => {}
      };

      const canvas = document.querySelector("#unity-game");

      (window as any).createUnityInstance(canvas, config)
        .then((unityInstance: any) => {
          (window as any).unityInstance = unityInstance;
        })
        .catch((error: any) => {
          console.error('Failed to load Unity game:', error);
        });
    });

    document.body.appendChild(loaderScript);
  }
}
