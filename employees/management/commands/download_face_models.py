"""KAYDAN SHIELD — Téléchargement des modèles InsightFace + SilentFace.

Usage typique :
    python manage.py download_face_models                  # InsightFace + check SilentFace
    python manage.py download_face_models --auto-convert   # + télécharge & convertit MiniFASNet
    python manage.py download_face_models --skip-silentface

Si seul SilentFace manque, la commande **renvoie un code 0** (warning uniquement)
pour ne pas bloquer le déploiement — le pipeline reco fonctionne sans liveness.
"""
from __future__ import annotations

import os
import ssl
from pathlib import Path
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand


def _build_ssl_context() -> ssl.SSLContext:
    """Contexte SSL avec le bundle CA de certifi (fix macOS Python "CERTIFICATE_VERIFY_FAILED")."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _download(url: str, dest: Path, chunk_size: int = 64 * 1024) -> None:
    """Télécharge ``url`` vers ``dest`` avec un contexte SSL certifi.

    Remplace urllib.urlretrieve qui ne sait pas passer de SSLContext custom
    et plante sur macOS quand le keystore système n'est pas accessible à Python.
    """
    ctx = _build_ssl_context()
    req = Request(url, headers={"User-Agent": "kaydan-shield/face-bootstrap"})
    with urlopen(req, context=ctx, timeout=120) as resp, open(dest, "wb") as fh:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            fh.write(chunk)


# URLs raw des poids .pth depuis le repo officiel Silent-Face-Anti-Spoofing
SILENTFACE_PTH_BASE = (
    "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/"
    "master/resources/anti_spoof_models"
)


class Command(BaseCommand):
    help = "Télécharge ou vérifie les modèles InsightFace + SilentFace MiniFASNet."

    def add_arguments(self, parser):
        parser.add_argument("--skip-insightface", action="store_true",
                            help="Saute le téléchargement InsightFace.")
        parser.add_argument("--skip-silentface", action="store_true",
                            help="Saute la vérification SilentFace.")
        parser.add_argument("--silentface-url", default="",
                            help="Base URL d'un mirror ONNX (terminée par /).")
        parser.add_argument("--auto-convert", action="store_true",
                            help="Télécharge les .pth officiels et convertit en .onnx via PyTorch.")

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        face_cfg = settings.KAYDAN_SHIELD["FACE"]
        insightface_ok = True
        silentface_ok = True

        if not opts["skip_insightface"]:
            insightface_ok = self._fetch_insightface(face_cfg)
        if not opts["skip_silentface"]:
            silentface_ok = self._fetch_silentface(
                face_cfg, opts["silentface_url"], opts["auto_convert"],
            )

        self.stdout.write("")
        if insightface_ok and silentface_ok:
            self.stdout.write(self.style.SUCCESS("[OK] Pipeline complet pret (reco + liveness)."))
            return
        if insightface_ok and not silentface_ok:
            self.stdout.write(self.style.WARNING(
                "[OK partiel] InsightFace pret, anti-spoofing indisponible."
            ))
            self.stdout.write(self.style.WARNING(
                "Le pipeline reco fonctionne sans liveness. Pour activer le liveness :"
            ))
            self.stdout.write("  - Re-essayer avec : python manage.py download_face_models --auto-convert")
            self.stdout.write("  - Ou desactiver : export FACE_LIVENESS_ENABLED=False")
            return
        # InsightFace KO → vrai blocage
        self.stderr.write(self.style.ERROR("[ECHEC] InsightFace KO — voir messages."))
        raise SystemExit(1)

    # ------------------------------------------------------------------
    def _fetch_insightface(self, face_cfg: dict) -> bool:
        name = face_cfg.get("MODEL_NAME", "buffalo_s")
        ctx_id = int(face_cfg.get("CTX_ID", -1))
        det_size = int(face_cfg.get("DET_SIZE", 640))
        root = face_cfg.get("MODEL_ROOT") or None

        self.stdout.write(self.style.NOTICE(
            f"-> InsightFace: prepare(name={name}, ctx_id={ctx_id})"
        ))
        try:
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            self.stderr.write(self.style.ERROR(
                f"   [X] insightface absent: {exc}"
            ))
            self.stderr.write("       pip install insightface onnxruntime")
            return False
        try:
            kwargs = {"name": name}
            if root:
                kwargs["root"] = root
            app = FaceAnalysis(**kwargs)
            app.prepare(ctx_id=ctx_id, det_size=(det_size, det_size))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"   [X] init: {exc}"))
            return False
        self.stdout.write(self.style.SUCCESS(f"   [OK] {name} pret."))
        return True

    # ------------------------------------------------------------------
    def _fetch_silentface(self, face_cfg: dict, base_url: str, auto_convert: bool) -> bool:
        lc = face_cfg.get("LIVENESS", {})
        if not lc.get("ENABLED", True):
            self.stdout.write(self.style.WARNING(
                "-> SilentFace: desactive (FACE_LIVENESS_ENABLED=False), skip."
            ))
            return True

        model_dir = Path(lc.get("MODEL_DIR", ""))
        model_dir.mkdir(parents=True, exist_ok=True)
        specs = lc.get("MODELS", [])

        self.stdout.write(self.style.NOTICE(
            f"-> SilentFace: verification ({len(specs)} modeles) dans {model_dir}"
        ))

        # Inventaire des manquants
        missing = []
        for fname, scale in specs:
            target = model_dir / fname
            if target.is_file() and target.stat().st_size > 1000:
                kb = target.stat().st_size / 1024
                self.stdout.write(self.style.SUCCESS(
                    f"   [OK] {fname} scale={scale} ({kb:.0f} Ko)"
                ))
            else:
                missing.append((fname, scale, target))
                self.stdout.write(self.style.WARNING(f"   [.] {fname} absent"))

        if not missing:
            return True

        # ── Option 1 : mirror URL fourni ──────────────────────────────
        if base_url:
            ok = True
            for fname, scale, target in missing:
                url = base_url.rstrip("/") + "/" + fname
                self.stdout.write(f"   Download {url}")
                try:
                    _download(url, target)
                    kb = target.stat().st_size / 1024
                    self.stdout.write(self.style.SUCCESS(f"   [OK] {fname} ({kb:.0f} Ko)"))
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"   [X] {fname}: {exc}"))
                    ok = False
            return ok

        # ── Option 2 : --auto-convert (.pth GitHub + PyTorch) ────────
        if auto_convert:
            return self._auto_convert_silentface(missing, model_dir)

        # ── Option 3 : juste afficher les instructions ───────────────
        self._print_instructions(model_dir)
        return False

    # ------------------------------------------------------------------
    def _auto_convert_silentface(self, missing, model_dir: Path) -> bool:
        """Télécharge les .pth officiels et convertit en .onnx via PyTorch."""
        self.stdout.write(self.style.NOTICE(
            "-> Auto-conversion .pth -> .onnx (necessite torch installe)"
        ))
        try:
            import torch  # noqa: F401
        except ImportError:
            self.stderr.write(self.style.ERROR(
                "   [X] PyTorch absent. Installer : pip install torch"
            ))
            self.stderr.write(
                "       Puis : python manage.py download_face_models --auto-convert"
            )
            return False

        # Vendoring des architectures MiniFASNet (sinon import depuis le repo)
        try:
            from employees._minifasnet import MiniFASNetV2, MiniFASNetV1SE
        except ImportError as exc:
            self.stderr.write(self.style.ERROR(
                f"   [X] employees/_minifasnet.py manquant: {exc}"
            ))
            return False

        arch_map = {
            "2.7_80x80_MiniFASNetV2.onnx":   ("2.7_80x80_MiniFASNetV2.pth",   MiniFASNetV2),
            "4_0_0_80x80_MiniFASNetV1SE.onnx": ("4_0_0_80x80_MiniFASNetV1SE.pth", MiniFASNetV1SE),
        }

        ok = True
        import torch
        for fname, scale, target in missing:
            if fname not in arch_map:
                self.stderr.write(self.style.ERROR(f"   [X] {fname}: pas d'arch connue."))
                ok = False
                continue
            pth_name, model_cls = arch_map[fname]
            pth_url = f"{SILENTFACE_PTH_BASE}/{pth_name}"
            pth_target = model_dir / pth_name
            try:
                self.stdout.write(f"   Download {pth_url}")
                _download(pth_url, pth_target)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"   [X] download {pth_name}: {exc}"))
                ok = False
                continue
            try:
                self.stdout.write(f"   Convert {pth_name} -> {fname}")
                state = torch.load(pth_target, map_location="cpu", weights_only=True)
                if isinstance(state, dict) and "state_dict" in state:
                    state = state["state_dict"]
                # Strip prefix "module." si entraîné en DataParallel
                state = {k.replace("module.", "", 1): v for k, v in state.items()}
                model = model_cls(embedding_size=128, conv6_kernel=(5, 5),
                                   drop_p=0.75, num_classes=3, img_channel=3)
                model.load_state_dict(state, strict=False)
                model.eval()
                dummy = torch.zeros(1, 3, 80, 80)
                torch.onnx.export(
                    model, dummy, target,
                    opset_version=11,
                    input_names=["input"], output_names=["logits"],
                    dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
                )
                # Cleanup .pth pour ne garder que les .onnx
                try:
                    pth_target.unlink()
                except OSError:
                    pass
                kb = target.stat().st_size / 1024
                self.stdout.write(self.style.SUCCESS(f"   [OK] {fname} ({kb:.0f} Ko)"))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"   [X] convert {fname}: {exc}"))
                ok = False
        return ok

    # ------------------------------------------------------------------
    def _print_instructions(self, model_dir: Path) -> None:
        """Affiche les instructions de fallback (3 options)."""
        sep = "-" * 60
        for line in [
            "",
            sep,
            "Pour obtenir les modeles SilentFace ONNX, 3 options :",
            "",
            "  1) AUTO-CONVERT (recommande, necessite pytorch installe)",
            "     pip install torch",
            "     python manage.py download_face_models --auto-convert",
            "",
            "  2) MIRROR (si tu as une URL hebergeant les .onnx)",
            "     python manage.py download_face_models \\",
            "         --silentface-url https://mon-mirror.example.com/silentface/",
            "",
            "  3) DESACTIVER LE LIVENESS (le pipeline reco continue de marcher)",
            "     Ajouter a ton .env :  FACE_LIVENESS_ENABLED=False",
            "",
            f"Destination des .onnx : {model_dir}",
            sep,
        ]:
            self.stdout.write(line)
