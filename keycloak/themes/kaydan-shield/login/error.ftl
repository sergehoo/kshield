<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=false; section>
    <#if section = "header">
        ${msg("errorTitle")!"Erreur"}
    <#elseif section = "form">
        <div id="kc-error-message" style="text-align:center;padding:8px 0">
            <div style="width:64px;height:64px;border-radius:50%;
                        background:rgba(248,113,113,.12);margin:0 auto 14px;
                        display:flex;align-items:center;justify-content:center">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
                     stroke="#f87171" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="15" y1="9" x2="9" y2="15"/>
                    <line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
            </div>
            <p class="instruction" style="font-size:14px;color:var(--ks-text-muted);line-height:1.5;margin:0 auto;max-width:340px">
                ${kcSanitize(message.summary)?no_esc}
            </p>
            <#if skipLink??>
            <#else>
                <#if client?? && client.baseUrl?has_content>
                    <p style="margin-top:24px">
                        <a id="backToApplication" href="${client.baseUrl}"
                           class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!}">
                            « ${kcSanitize(msg("backToApplication"))?no_esc}
                        </a>
                    </p>
                </#if>
            </#if>
        </div>
    </#if>
</@layout.registrationLayout>
