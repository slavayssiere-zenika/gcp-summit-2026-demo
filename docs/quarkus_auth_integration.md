# Guide d'Intégration de l'Authentification pour les Microservices Quarkus

Ce guide documente la mise en œuvre du système d'authentification de la plateforme Zenika Console Agent pour un microservice développé en **Quarkus**. Ce système repose sur :
1. La validation d'un token JWT signé avec l'algorithme symétrique **HS256** via une clé partagée (`SECRET_KEY`).
2. Le support de la double transmission : via l'en-tête `Authorization: Bearer <token>` et via le cookie `access_token`.
3. La validation d'un token Google OIDC (pour les invocations Cloud Scheduler, Cloud Pub/Sub, etc.).
4. La propagation automatique de l'en-tête d'authentification pour les requêtes inter-services (Zero-Trust).

---

## 📦 1. Dépendances requises

Pour gérer l'authentification et les appels HTTP sortants de façon réactive, ajoutez les dépendances suivantes dans votre `pom.xml` (ou équivalent Gradle) :

### Maven (`pom.xml`)

```xml
<dependencies>
    <!-- Serveur Web Réactif (standard de la plateforme) -->
    <dependency>
        <groupId>io.quarkus</groupId>
        <artifactId>quarkus-resteasy-reactive</artifactId>
    </dependency>
    <dependency>
        <groupId>io.quarkus</groupId>
        <artifactId>quarkus-resteasy-reactive-jackson</artifactId>
    </dependency>

    <!-- Quarkus Security (Gestion de l'identité et du contexte de sécurité) -->
    <dependency>
        <groupId>io.quarkus</groupId>
        <artifactId>quarkus-security</artifactId>
    </dependency>

    <!-- Jose4j (Validation JWT légère et robuste) -->
    <dependency>
        <groupId>org.bitbucket.b_c</groupId>
        <artifactId>jose4j</artifactId>
        <version>0.9.6</version>
    </dependency>

    <!-- Client HTTP OIDC Google (Optionnel : requis pour VerifyOIDC) -->
    <dependency>
        <groupId>com.google.api-client</groupId>
        <artifactId>google-api-client</artifactId>
        <version>2.2.0</version>
        <exclusions>
            <!-- Exclusion pour éviter les conflits de logging avec Quarkus/JBoss -->
            <exclusion>
                <groupId>commons-logging</groupId>
                <artifactId>commons-logging</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
    
    <!-- Client REST MicroProfile (pour la propagation réactive) -->
    <dependency>
        <groupId>io.quarkus</groupId>
        <artifactId>quarkus-rest-client-reactive-jackson</artifactId>
    </dependency>
</dependencies>
```

---

## ⚙️ 2. Configuration (`application.properties`)

Ajoutez ces configurations pour forcer le verrouillage Zero-Trust par défaut et activer la propagation des headers.

```properties
# 1. Protection Zero-Trust : Verrouille toutes les routes par défaut.
# Tout endpoint sans annotation de sécurité (@PermitAll, @RolesAllowed) renverra un HTTP 401.
quarkus.security.deny-unannotated-members=true

# 2. Propagation automatique de l'authentification pour les clients REST MicroProfile.
# Quarkus propagera automatiquement l'en-tête Authorization vers les appels sortants.
org.eclipse.microprofile.rest.client.propagateHeaders=Authorization
```

---

## 🛡️ 3. Mécanisme d'Authentification Customisé

Conformément aux exigences de la plateforme (cookie + header + signature symétrique HS256 + leeway de 300s + vérification du claim `sub`), nous implémentons un `HttpAuthenticationMechanism` Quarkus personnalisé.

Créez le fichier [PlatformAuthMechanism.java](file:///src/main/java/fr/zenika/platform/auth/PlatformAuthMechanism.java) :

```java
package fr.zenika.platform.auth;

import io.quarkus.security.identity.IdentityProviderManager;
import io.quarkus.security.identity.SecurityIdentity;
import io.quarkus.security.identity.request.AuthenticationRequest;
import io.quarkus.security.identity.request.TrustedAuthenticationRequest;
import io.quarkus.security.runtime.QuarkusPrincipal;
import io.quarkus.security.runtime.QuarkusSecurityIdentity;
import io.quarkus.vertx.http.runtime.security.ChallengeData;
import io.quarkus.vertx.http.runtime.security.HttpAuthenticationMechanism;
import io.smallrye.mutiny.Uni;
import io.vertx.ext.web.RoutingContext;
import jakarta.annotation.Priority;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.inject.Alternative;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.jose4j.jwk.HmacKey;
import org.jose4j.jwt.JwtClaims;
import org.jose4j.jwt.consumer.InvalidJwtException;
import org.jose4j.jwt.consumer.JwtConsumer;
import org.jose4j.jwt.consumer.JwtConsumerBuilder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.util.Collections;
import java.util.Optional;
import java.util.Set;

@Alternative
@Priority(1)
@ApplicationScoped
public class PlatformAuthMechanism implements HttpAuthenticationMechanism {

    private static final Logger log = LoggerFactory.getLogger(PlatformAuthMechanism.class);
    private static final String BEARER_PREFIX = "Bearer ";
    private static final String COOKIE_NAME = "access_token";

    @ConfigProperty(name = "SECRET_KEY")
    String secretKey;

    @Override
    public Uni<SecurityIdentity> authenticate(RoutingContext context, IdentityProviderManager identityProviderManager) {
        // Extraction du token (depuis Header Authorization ou Cookie access_token)
        String token = extractToken(context);

        if (token == null) {
            // Pas de token fourni -> Identité anonyme (sera bloquée sur les routes sécurisées)
            return Uni.createFrom().item(QuarkusSecurityIdentity.builder().anonymous(true).build());
        }

        try {
            // Validation et décodage du JWT HS256
            JwtClaims claims = validateToken(token);
            String subject = claims.getSubject();

            if (subject == null || subject.trim().isEmpty()) {
                log.warn("Token invalide : claim 'sub' manquant ou vide");
                return Uni.createFrom().failure(new SecurityException("Claim 'sub' vide ou absent"));
            }

            String role = claims.getStringClaimValue("role");
            QuarkusSecurityIdentity.Builder builder = QuarkusSecurityIdentity.builder()
                    .setPrincipal(new QuarkusPrincipal(subject))
                    .addCredential(new TrustedAuthenticationRequest(subject).getCredential());

            if (role != null && !role.trim().isEmpty()) {
                builder.addRole(role.trim());
            } else {
                builder.addRole("user"); // Rôle par défaut
            }

            // Conserver le payload décodé dans les attributs de sécurité si besoin
            builder.addAttribute("claims", claims);

            // Mettre en cache dans la requête pour la propagation réactive
            context.put("Authorization", BEARER_PREFIX + token);

            return Uni.createFrom().item(builder.build());

        } catch (InvalidJwtException e) {
            log.warn("Échec de validation du token JWT : {}", e.getMessage());
            // Optionnel : Si besoin d'un fallback OIDC Google (ex: scheduler), implémenter ici
            return Uni.createFrom().failure(new SecurityException("Token invalide ou expiré"));
        } catch (Exception e) {
            log.error("Erreur critique d'authentification :", e);
            return Uni.createFrom().failure(new SecurityException("Erreur de sécurité interne"));
        }
    }

    private String extractToken(RoutingContext context) {
        // 1. Recherche dans le Header Authorization
        String authHeader = context.request().getHeader("Authorization");
        if (authHeader != null && authHeader.startsWith(BEARER_PREFIX)) {
            return authHeader.substring(BEARER_PREFIX.length()).trim();
        }

        // 2. Recherche dans le Cookie access_token
        var cookie = context.request().getCookie(COOKIE_NAME);
        if (cookie != null) {
            return cookie.getValue().trim();
        }

        return null;
    }

    private JwtClaims validateToken(String token) throws Exception {
        Key key = new HmacKey(secretKey.getBytes(StandardCharsets.UTF_8));

        JwtConsumer jwtConsumer = new JwtConsumerBuilder()
                .setRequireExpirationTime()
                .setAllowedClockSkewInSeconds(300) // Leeway de 300 secondes (5 min) conforme à shared.auth.jwt
                .setVerificationKey(key)
                .build();

        return jwtConsumer.processToClaims(token);
    }

    @Override
    public Uni<ChallengeData> getChallenge(RoutingContext context) {
        // Challenge standard 401 Unauthorized
        ChallengeData challenge = new ChallengeData(401, "WWW-Authenticate", BEARER_PREFIX.trim());
        return Uni.createFrom().item(challenge);
    }

    @Override
    public Set<Class<? extends AuthenticationRequest>> getCredentialTypes() {
        return Collections.singleton(TrustedAuthenticationRequest.class);
    }
}
```

---

## ⚡ 4. Support Google OIDC (VerifyOIDC) pour les Schedulers et Triggers Pub/Sub

Si votre microservice doit être invoqué par des composants système GCP (comme Cloud Scheduler ou un Push Pub/Sub), implémentez un validateur de token OIDC Google.

Créez le fichier [GoogleOidcVerifier.java](file:///src/main/java/fr/zenika/platform/auth/GoogleOidcVerifier.java) :

```java
package fr.zenika.platform.auth;

import com.google.api.client.googleapis.auth.oauth2.GoogleIdToken;
import com.google.api.client.googleapis.auth.oauth2.GoogleIdTokenVerifier;
import com.google.api.client.http.javanet.NetHttpTransport;
import com.google.api.client.json.gson.GsonFactory;
import jakarta.enterprise.context.ApplicationScoped;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Collections;

@ApplicationScoped
public class GoogleOidcVerifier {

    private static final Logger log = LoggerFactory.getLogger(GoogleOidcVerifier.class);
    
    private final GoogleIdTokenVerifier verifier;

    public GoogleOidcVerifier() {
        this.verifier = new GoogleIdTokenVerifier.Builder(new NetHttpTransport(), new GsonFactory()).build();
    }

    public GoogleIdToken.Payload verify(String oidcToken) throws Exception {
        GoogleIdToken idToken = verifier.verify(oidcToken);
        if (idToken == null) {
            throw new SecurityException("Token OIDC Google invalide ou expiré");
        }

        GoogleIdToken.Payload payload = idToken.getPayload();
        String email = payload.getEmail();

        // Validation du Service Account appelant (Zero-Trust)
        if (!isServiceAccountAllowed(email)) {
            log.warn("[OIDC] Service Account non autorisé : {}", email);
            throw new SecurityException("Service Account non autorisé");
        }

        return payload;
    }

    private boolean isServiceAccountAllowed(String email) {
        String invokerSa = System.getenv("PUBSUB_INVOKER_SA_EMAIL");
        String cvSa = System.getenv("CV_SA_EMAIL");
        String schedulerSa = System.getenv("SCHEDULER_SA_EMAIL");

        return email.equals(invokerSa) || email.equals(cvSa) || email.equals(schedulerSa);
    }
}
```

> [!NOTE]
> Vous pouvez intégrer ce validateur dans `PlatformAuthMechanism.java` pour gérer le fallback en cas d'échec du décodage du JWT HS256 standard.

---

## 🔒 5. Sécuriser les Endpoints (JAX-RS)

Grâce à `quarkus.security.deny-unannotated-members=true`, tout endpoint non annoté est fermé. Vous devez expliciter l'accès :

```java
package fr.zenika.platform.resource;

import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/items")
@Produces(MediaType.APPLICATION_JSON)
public class ItemResource {

    // Route ouverte pour les health checks et métriques
    @GET
    @Path("/health")
    @PermitAll
    public String health() {
        return "OK";
    }

    // Route protégée : Nécessite un JWT valide avec le rôle "admin"
    @GET
    @Path("/admin-config")
    @RolesAllowed("admin")
    public String getAdminConfig() {
        return "Confidentiel";
    }

    // Route protégée générique : Nécessite n'importe quel rôle valide (ex: user)
    @GET
    @RolesAllowed({"user", "admin"})
    public String getItems() {
        return "Liste d'items";
    }
}
```

---

## 🔄 6. Propagation du JWT aux services tiers (Zero-Trust)

Pour appeler un autre microservice (ex: `users_api` ou `competencies_api`) en transmettant le JWT d'origine, utilisez le client REST réactif de Quarkus.

### Déclarer le Client REST

Utilisez l'annotation `@RegisterClientHeaders` combinée à la configuration de propagation de Quarkus :

```java
package fr.zenika.platform.client;

import org.eclipse.microprofile.rest.client.annotation.RegisterClientHeaders;
import org.eclipse.microprofile.rest.client.inject.RegisterRestClient;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;

@RegisterRestClient(configKey = "users-api")
@RegisterClientHeaders // Hérite automatiquement de la propagation configurée dans application.properties
@Path("/users")
public interface UserClient {

    @GET
    @Path("/{userId}")
    UserDto getUserById(@PathParam("userId") String userId);
}
```

---

## 🧪 7. Tests d'intégration et Sécurité

Quarkus propose l'extension `@TestSecurity` pour injecter des identités fictives sans avoir à générer de vrais tokens JWT dans vos tests unitaires ou d'intégration.

```java
package fr.zenika.platform;

import io.quarkus.test.junit.QuarkusTest;
import io.quarkus.test.security.TestSecurity;
import org.junit.jupiter.api.Test;

import static io.restassured.RestAssured.given;
import static org.hamcrest.CoreMatchers.is;

@QuarkusTest
public class ItemResourceTest {

    @Test
    public void testHealthEndpointOpen() {
        given()
          .when().get("/items/health")
          .then()
             .statusCode(200)
             .body(is("OK"));
    }

    @Test
    public void testSecureEndpointReturns401WithoutToken() {
        given()
          .when().get("/items")
          .then()
             .statusCode(401);
    }

    @Test
    @TestSecurity(user = "user@zenika.com", roles = {"user"})
    public void testSecureEndpointSuccessWithUser() {
        given()
          .when().get("/items")
          .then()
             .statusCode(200);
    }

    @Test
    @TestSecurity(user = "admin@zenika.com", roles = {"admin"})
    public void testAdminEndpointSuccessWithAdmin() {
        given()
          .when().get("/items/admin-config")
          .then()
             .statusCode(200);
    }
}
```
