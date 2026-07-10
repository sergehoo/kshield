/**
 * DownloadPackageModal — Modale de téléchargement du package Edge Gateway.
 *
 * Permet à l'admin de choisir la plateforme cible (Windows, Linux, Docker, etc.)
 * puis télécharge un ZIP personnalisé avec :
 *   - la config gateway_id + activation_token pré-injectée
 *   - le script d'installation OS-spécifique
 *   - un README
 *
 * Le download se fait via un blob pour pouvoir montrer un spinner et un
 * message de succès (rotation du activation_token à chaque call).
 */
import { useState } from "react";
import toast from "react-hot-toast";
import {
  Download, Monitor, HardDrive, Container, Cpu, Apple, Package2, X,
} from "lucide-react";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { edgeGatewayService } from "@/services/enrollment";

interface Props {
  gatewayId: string;
  gatewayLabel: string;
  open: boolean;
  onClose: () => void;
}

// ─── Catalogue de plateformes ────────────────────────────────────
interface PlatformDef {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  recommended?: boolean;
  size?: string;
}

const PLATFORMS: PlatformDef[] = [
  {
    id: "windows_exe",
    label: "Windows",
    description: "Installateur .exe — Windows 10/11 + Server. Service auto-start.",
    icon: <Monitor className="w-5 h-5" />,
    recommended: true,
    size: "~4 MB",
  },
  {
    id: "linux_deb",
    label: "Linux (Ubuntu/Debian)",
    description: "Package .deb avec service systemd. Compatible Ubuntu 20.04+.",
    icon: <HardDrive className="w-5 h-5" />,
    recommended: true,
    size: "~4 MB",
  },
  {
    id: "linux_rpm",
    label: "Linux (RHEL/Fedora/AlmaLinux)",
    description: "Package .rpm avec service systemd. Compatible RHEL 8+.",
    icon: <HardDrive className="w-5 h-5" />,
    size: "~4 MB",
  },
  {
    id: "linux_sh",
    label: "Linux (Script universel)",
    description: "Script bash — fonctionne sur toute distribution avec systemd.",
    icon: <HardDrive className="w-5 h-5" />,
    size: "~4 MB",
  },
  {
    id: "macos_pkg",
    label: "macOS",
    description: "Bundle avec launchd — Intel + Apple Silicon.",
    icon: <Apple className="w-5 h-5" />,
    size: "~4 MB",
  },
  {
    id: "docker",
    label: "Docker Compose",
    description: "docker-compose.yml prêt à l'emploi — un simple 'docker compose up -d'.",
    icon: <Container className="w-5 h-5" />,
    size: "~4 MB",
  },
  {
    id: "raspberry_pi",
    label: "Raspberry Pi",
    description: "Optimisé Raspberry Pi 4/5 (ARM64). Faible empreinte mémoire.",
    icon: <Cpu className="w-5 h-5" />,
    size: "~4 MB",
  },
  {
    id: "mini_pc",
    label: "Mini PC industriel",
    description: "Debian/Ubuntu embarqué — Advantech, Beelink, x86.",
    icon: <Package2 className="w-5 h-5" />,
    size: "~4 MB",
  },
];

export function DownloadPackageModal({ gatewayId, gatewayLabel, open, onClose }: Props) {
  const [downloading, setDownloading] = useState<string | null>(null);

  const handleDownload = async (platformId: string) => {
    setDownloading(platformId);
    try {
      const response = await edgeGatewayService.downloadPackageBlob(gatewayId, platformId);
      // response.data est un Blob
      const blob = new Blob([response.data as any], { type: "application/zip" });
      const url = URL.createObjectURL(blob);

      // Récupère le nom du fichier depuis Content-Disposition ou fallback
      const disposition = response.headers?.["content-disposition"] || "";
      const nameMatch = disposition.match(/filename="([^"]+)"/);
      const filename = nameMatch?.[1]
        ?? `KaydanEdgeGateway-${gatewayLabel}-${platformId}.zip`;

      // Déclenche le download natif
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      toast.success(`Package ${platformId} téléchargé — token d'activation valide 72h`);
    } catch (err: any) {
      toast.error(`Échec du téléchargement : ${err?.response?.data?.error ?? err.message}`);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={`Télécharger le package — ${gatewayLabel}`} size="lg">
      <div className="space-y-4">
        <div className="bg-info/10 border border-info/30 rounded-md p-3 text-sm">
          <p className="font-medium mb-1">Choisissez votre plateforme cible</p>
          <p className="text-ink-muted">
            Chaque téléchargement génère un ZIP unique avec le <code>gateway_id</code>{" "}
            et un <code>activation_token</code> à usage unique (valide 72h).{" "}
            Une fois installé, le service se connectera automatiquement au cloud.
          </p>
        </div>

        <div className="grid gap-2">
          {PLATFORMS.map((p) => {
            const isDownloading = downloading === p.id;
            return (
              <div
                key={p.id}
                className="flex items-center gap-3 p-3 border rounded-md hover:bg-muted/50 transition-colors"
              >
                <div className="text-brand-500 shrink-0">{p.icon}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{p.label}</span>
                    {p.recommended && (
                      <span className="text-[10px] px-1.5 py-0.5 bg-success/20 text-success rounded">
                        RECOMMANDÉ
                      </span>
                    )}
                    {p.size && (
                      <span className="text-xs text-ink-muted">· {p.size}</span>
                    )}
                  </div>
                  <p className="text-xs text-ink-muted mt-0.5">{p.description}</p>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => handleDownload(p.id)}
                  disabled={isDownloading || downloading !== null}
                >
                  <Download className="w-4 h-4 mr-1" />
                  {isDownloading ? "..." : "Télécharger"}
                </Button>
              </div>
            );
          })}
        </div>

        <div className="text-xs text-ink-muted border-t pt-3">
          <strong>Sécurité :</strong> ne partagez PAS le fichier ZIP téléchargé —
          il contient un token d'activation qui donne accès à votre organisation.{" "}
          Le token est à usage unique : dès qu'un premier appareil s'active,
          il devient invalide.
        </div>

        <div className="flex justify-end">
          <Button variant="secondary" onClick={onClose}>
            <X className="w-4 h-4 mr-1" /> Fermer
          </Button>
        </div>
      </div>
    </Modal>
  );
}
