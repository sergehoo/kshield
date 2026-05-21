<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=realm.password && realm.registrationAllowed && !registrationDisabled??; section>

    <#if section = "header">
        ${msg("loginAccountTitle")}
    <#elseif section = "form">
        <div id="kc-form">
          <div id="kc-form-wrapper">

            <#-- ═══════════════════════════════════════════════════════════
                 Formulaire principal email + password
                 ═══════════════════════════════════════════════════════════ -->
            <#if realm.password>
                <form id="kc-form-login" onsubmit="login.disabled = true; return true;"
                      action="${url.loginAction}" method="post">

                    <#if !usernameHidden??>
                        <div class="form-group">
                            <label for="username" class="${properties.kcLabelClass!}">
                                <#if !realm.loginWithEmailAllowed>${msg("username")}
                                <#elseif !realm.registrationEmailAsUsername>${msg("usernameOrEmail")}
                                <#else>${msg("email")}</#if>
                            </label>
                            <input tabindex="1" id="username" name="username"
                                   value="${(login.username!'')}"
                                   type="text" autofocus autocomplete="off"
                                   class="${properties.kcInputClass!}"
                                   aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>" />
                            <#if messagesPerField.existsError('username','password')>
                                <span class="kc-feedback-text" aria-live="polite">
                                    ${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}
                                </span>
                            </#if>
                        </div>
                    </#if>

                    <div class="form-group">
                        <label for="password" class="${properties.kcLabelClass!}">${msg("password")}</label>
                        <input tabindex="2" id="password" name="password" type="password"
                               autocomplete="current-password"
                               class="${properties.kcInputClass!}"
                               aria-invalid="<#if messagesPerField.existsError('username','password')>true</#if>" />
                    </div>

                    <div class="form-group" id="kc-form-options">
                        <#if realm.rememberMe && !usernameHidden??>
                            <div class="checkbox">
                                <label>
                                    <#if login.rememberMe??>
                                        <input tabindex="3" id="rememberMe" name="rememberMe" type="checkbox" checked> ${msg("rememberMe")}
                                    <#else>
                                        <input tabindex="3" id="rememberMe" name="rememberMe" type="checkbox"> ${msg("rememberMe")}
                                    </#if>
                                </label>
                            </div>
                        </#if>
                        <#if realm.resetPasswordAllowed>
                            <span><a tabindex="5" href="${url.loginResetCredentialsUrl}">${msg("doForgotPassword")}</a></span>
                        </#if>
                    </div>

                    <div id="kc-form-buttons" class="form-group">
                        <input type="hidden" id="id-hidden-input" name="credentialId"
                               <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>/>
                        <input tabindex="4" class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}"
                               name="login" id="kc-login" type="submit" value="${msg("doLogIn")}"/>
                    </div>
                </form>
            </#if>
          </div>
        </div>

    <#elseif section = "info" >
        <#-- ─── Section sociale (Microsoft Entra ID, etc.) ─── -->
        <#if realm.password && social.providers??>
            <div id="kc-social-providers" class="${properties.kcFormSocialAccountSectionClass!}">
                <hr/>
                <h2 style="font-size:13px;color:var(--ks-text-dim);text-align:center;
                           text-transform:uppercase;letter-spacing:.06em;font-weight:600;">
                    ${msg("identity-provider-login-label")}
                </h2>
                <ul class="${properties.kcFormSocialAccountListClass!} <#if social.providers?size gt 3>${properties.kcFormSocialAccountListGridClass!}</#if>">
                    <#list social.providers as p>
                        <a id="social-${p.alias}"
                           class="${properties.kcFormSocialAccountListButtonClass!}"
                           href="${p.loginUrl}">
                            <#if p.iconClasses?has_content>
                                <i class="${properties.kcCommonLogoIdP!} ${p.iconClasses!}" aria-hidden="true"></i>
                            </#if>
                            <span>${p.displayName!}</span>
                        </a>
                    </#list>
                </ul>
            </div>
        </#if>

        <#-- ─── Footer KAYDAN ─── -->
        <div class="kaydan-footer" style="margin-top:18px">
            KAYDAN GROUPE © ${.now?string("yyyy")} — Solution propriétaire
        </div>

        <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
            <div id="kc-registration-container">
                <div id="kc-registration">
                    <span>${msg("noAccount")} <a tabindex="6" href="${url.registrationUrl}">${msg("doRegister")}</a></span>
                </div>
            </div>
        </#if>
    </#if>

</@layout.registrationLayout>
