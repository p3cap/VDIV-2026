Vadász Dénes Informatikai Verseny - 2026 - Mars rover

█ █ █ █ █ █ ▀█ █
█▀█ █▄█ █▀█  ▄ ▄
csapat munkája

======== Verseny információ =======

Csapat neve: huh?!
Csapatagok nevei: Dobosi Péter, Kovács Dávid, Torontáli Ádám
Iskola: BMSZC Puskás Tivadar Távközlési és Informatikai Technikum
Felkészítő tanár: Zámbó Dominik
Elérhetőségek:
  - Dobosi Péter Dániel: dobosipetidani@gmail.com 
  - Torontáli Ádám: torontaliadi07@gmail.com
  - Kovács Dávid: kovacs.david8002@gmail.com
- programfejlesztői környezetek és verziói**: Python3.13, javascript-ES2025, c++ (opcionális)


======== Szükségek szoftverek ========
- Python 3.13 vagy újabb verziója (https://www.python.org/downloads/)
- node.js (https://nodejs.org/en/download)

- C++ (Visual Studio-ban egy modify-t kell indítani és a c++ desktop developer kiegésztőt letölteni) [opcionális, gyorsabb machine learning model képzéshez érdemes használni]


======== Futtatás ========

Telepísd le a függőségeket: python3 setup_deps.py
Program indítása: python3 run_dev.py


======== Használati Útmutató ========

A futtatás után a terminálban ki kell választani a futtatási opciókat, majd
a program elindítja a Szimulációt, a szervert és a dashboardot, majd megnyitja a frontented böngészőben.

Új szimuláció futtatásához nyomj ENTER-t a run_dev terminálba, vagy zárd be, hogy leállítsa a folyamatokat,
melőtt újra elindítot a run dev fájlt


======== Dokumentáció ========

Részletesebb dokumentáció megtalálható a dashboard (a run_dev után megnyitott böngésző ablak) dokumentáció szekciójában,
illetve a dashboard/src/doc/hu mappában


Megjegyzés: 
  A machine learning ppo model képzése, optimális erőforrásokkal, idővel és a megfelelő környezetben képes a legoptimálisabb taktikát megtalálni
  Mivel erre nem volt lehetőségünk, ezért kidolgoztunk egy megbízhatóbb algoritmust a bányászásra, ezt indításkor a brain opcióval lehet futtatni.
  A PPO_machine_learning_doc.md dokumentáció tartalmazza a machine learning működését.