---
name: hexagonal-architecture
description: Design, implement, and refactor Ports & Adapters systems with clear domain boundaries, dependency inversion, and testable use-case orchestration across TypeScript, Java, Kotlin, and Go services.
origin: ECC
---

# Hexagonal Architecture

Hexagonal architecture (Ports and Adapters) keeps business logic independent from frameworks, transport, and persistence details. The core app depends on abstract ports, and adapters implement those ports at the edges.

## When to Use

- Building new features where long-term maintainability and testability matter.
- Refactoring layered or framework-heavy code where domain logic is mixed with I/O concerns.
- Supporting multiple interfaces for the same use case (HTTP, CLI, queue workers, cron jobs).
- Replacing infrastructure (database, external APIs, message bus) without rewriting business rules.

## Core Concepts

- **Domain model**: Business rules and entities/value objects. No framework imports.
- **Use cases (application layer)**: Orchestrate domain behavior and workflow steps.
- **Inbound ports**: Contracts describing what the application can do.
- **Outbound ports**: Contracts for dependencies the application needs (repositories, gateways, event publishers).
- **Adapters**: Infrastructure and delivery implementations of ports.
- **Composition root**: Single wiring location where concrete adapters are bound to use cases.

Dependency direction is always **inward**:
- Adapters → application/domain
- Application → port interfaces
- Domain → nothing external

## How It Works

**Step 1: Model a use case boundary** — Define a single use case with clear input/output DTOs. Keep transport details outside this boundary.

**Step 2: Define outbound ports first** — Identify every side effect as a port: persistence, external calls, cross-cutting concerns.

**Step 3: Implement the use case with pure orchestration** — Receives ports via constructor. Validates invariants, coordinates domain rules, returns plain data.

**Step 4: Build adapters at the edge** — Inbound adapter converts protocol input. Outbound adapter maps app contracts to concrete APIs/ORM.

**Step 5: Wire everything in a composition root** — Instantiate adapters, inject into use cases. Keep wiring centralized.

**Step 6: Test per boundary** — Unit test use cases with fake ports. Integration test adapters with real infra.

## Java Package Layout

```
src/main/java/com/example/feature/
  domain/
    Order.java
    OrderPolicy.java
  application/
    port/in/
      CreateOrderUseCase.java
    port/out/
      OrderRepositoryPort.java
      PaymentGatewayPort.java
    usecase/
      CreateOrderUseCaseImpl.java
  adapter/
    in/
      http/
        OrderController.java
    out/
      persistence/
        JpaOrderRepository.java
      payment/
        StripePaymentGateway.java
```

## Java Example

**Port definitions**

```java
// application/port/out/OrderRepositoryPort.java
public interface OrderRepositoryPort {
    void save(Order order);
    Optional<Order> findById(OrderId id);
}

// application/port/in/CreateOrderUseCase.java
public interface CreateOrderUseCase {
    CreateOrderResult execute(CreateOrderCommand command);
}
```

**Use case**

```java
public class CreateOrderUseCaseImpl implements CreateOrderUseCase {
    private final OrderRepositoryPort orderRepository;
    private final PaymentGatewayPort paymentGateway;

    public CreateOrderUseCaseImpl(OrderRepositoryPort orderRepo, PaymentGatewayPort paymentGateway) {
        this.orderRepository = orderRepo;
        this.paymentGateway = paymentGateway;
    }

    @Override
    public CreateOrderResult execute(CreateOrderCommand command) {
        Order order = Order.create(command.orderId(), command.amountCents());
        PaymentAuth auth = paymentGateway.authorize(order.getId(), order.getAmountCents());
        Order authorized = order.markAuthorized(auth.authorizationId()); // returns new instance
        orderRepository.save(authorized);
        return new CreateOrderResult(order.getId(), auth.authorizationId());
    }
}
```

**Outbound adapter**

```java
public class JpaOrderRepository implements OrderRepositoryPort {
    private final OrderJpaRepository jpa;

    @Override
    public void save(Order order) {
        jpa.save(OrderMapper.toEntity(order));
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return jpa.findById(id.value()).map(OrderMapper::toDomain);
    }
}
```

**Composition root**

```java
@Configuration
public class OrdersConfig {
    @Bean
    public CreateOrderUseCase createOrderUseCase(OrderRepositoryPort repo, PaymentGatewayPort gateway) {
        return new CreateOrderUseCaseImpl(repo, gateway);
    }
}
```

## Anti-Patterns to Avoid

- Domain entities importing ORM models, web framework types, or SDK clients.
- Use cases reading directly from HTTP request/response objects.
- Returning database rows directly from use cases.
- Adapters calling each other directly instead of flowing through use-case ports.
- Spreading dependency wiring across many files with hidden global singletons.

## Migration Playbook

1. Pick one vertical slice (single endpoint/job) with frequent change pain.
2. Extract a use-case boundary with explicit input/output types.
3. Introduce outbound ports around existing infrastructure calls.
4. Move orchestration logic from controllers/services into the use case.
5. Keep old adapters, but make them delegate to the new use case.
6. Add tests around the new boundary (unit + adapter integration).
7. Repeat slice-by-slice; avoid full rewrites.

## Testing Guidance

- **Domain tests**: test entities/value objects as pure business rules (no mocks).
- **Use-case unit tests**: test orchestration with fakes/stubs for outbound ports.
- **Outbound adapter contract tests**: define shared contract suites at port level.
- **Inbound adapter tests**: verify protocol mapping to use-case input.
- **Adapter integration tests**: run against real infrastructure.

## Best Practices Checklist

- Domain and use-case layers import only internal types and ports.
- Every external dependency is represented by an outbound port.
- Validation occurs at boundaries (inbound adapter + use-case invariants).
- Use immutable transformations (return new values/entities instead of mutating).
- Errors are translated across boundaries (infra errors → domain errors).
- Composition root is explicit and easy to audit.
- Use cases are testable with simple in-memory fakes for ports.
