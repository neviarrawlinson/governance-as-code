1. Do GRC professionals need to know how to code to implement Governance as Code?

Not necessarily. I think it's more important to understand how technical systems operate, how to define measurable requirements, and how to communicate those requirements to engineering teams. AI tools can also help bridge some of that technical knowledge gap. You don't have to become a software engineer to contribute to engineering governance.

2. What's the difference between Governance as Code and Policy as Code?

I view Policy as Code as one component of a broader Governance as Code approach. Policy as Code focuses primarily on translating policies into executable rules. Governance as Code extends that into ownership, approvals, exceptions, evidence, accountability, and continuous assurance.

3. How do you prevent AI agents from bypassing governance controls?

The enforcement mechanism needs to operate independently of the AI model. We shouldn't rely entirely on prompts to enforce security requirements. The agent's permissions, access to systems, and execution capabilities should be restricted through technical controls that the agent cannot independently modify.

4. How do we maintain human oversight without slowing down AI automation?

I would take a risk-based approach. Not every action requires human approval. Low-risk activities can potentially be automated, while higher-risk activities require additional authorization. The important thing is defining those boundaries upfront rather than making those decisions after something goes wrong.

5. How does this approach address AI hallucinations?

It doesn't eliminate hallucinations, but it can help reduce their operational impact. By separating the AI's recommendation from the authorization and execution process, we can validate proposed actions before allowing them to occur. We still need additional controls to validate the accuracy of AI-generated information.

6. How would this work with existing GRC platforms like ServiceNow or Archer?

I'm not advocating for organizations to replace their existing GRC platforms. I would look at how we can integrate automated control testing, technical enforcement, and evidence generation with those platforms. Ideally, we're reducing manual activities rather than creating another disconnected governance process.

7. How does this approach align with NIST AI RMF or ISO 42001?

These frameworks help organizations establish governance expectations and risk management practices. Governance as Code can help operationalize some of those expectations by translating them into measurable requirements, workflows, technical controls, and evidence. It's an implementation approach, not a replacement for the frameworks.

8. Who should own Governance as Code — GRC or engineering?

I think it requires shared ownership. GRC helps define the requirements and assurance expectations. Engineering helps implement and maintain the technical mechanisms. Business and risk owners remain accountable for their respective decisions. This shouldn't become another responsibility assigned entirely to InfoSec.

9. What happens if the automated governance rules are incorrect?

That's why we need version control, peer reviews, testing, change management, and ongoing monitoring. Governance logic can contain errors just like any other software. We need controls over the controls themselves.

10. Is your GitHub proof of concept production-ready?

No, and that's intentional. I built it as an educational proof of concept using simulated data to demonstrate how these concepts could work. A production implementation would require additional security controls, integrations, testing, monitoring, and organizational requirements.

11. Did you use AI to build your prototype?

If asked this, distinguish between using AI to assist with development and having AI operate within the prototype. The MFA example uses deterministic testing logic, and the governed-access prototype demonstrates simulated requests and independent authorization decisions. The governance decision does not depend on an AI model's judgment.

12. Can smaller organizations implement this without a significant budget?

Absolutely. Many of these capabilities are available through open-source tools or platforms organizations already use. I would start with one control, one reliable source of evidence, and one automated evaluation. You don't need to purchase an enterprise platform to begin experimenting with these concepts.

13. Does hashing evidence make it tamper-proof?

Not necessarily. Hashing helps us detect whether evidence has changed when compared against a trusted original hash. It doesn't prevent someone from modifying the evidence, and it doesn't guarantee the original information was accurate. That's why we still need appropriate storage, access controls, and evidence management practices.

14. Can AI eventually replace GRC professionals?

I think AI will change how GRC professionals work. Many repetitive activities, such as evidence collection and initial control assessments, can become more automated. But interpreting organizational risk, establishing accountability, making risk acceptance decisions, and exercising professional judgment remain important responsibilities.

15. What is the biggest barrier to implementing Governance as Code?

I don't necessarily think it's the technology. I think it's the disconnect between governance and engineering teams. If our requirements are ambiguous or interpreted differently across departments, automating them doesn't solve that problem. It can actually amplify it.

16. Where can we learn more or access your examples?

I've made my Governance as Code repository publicly available on GitHub. It includes practical examples that people can explore and build upon. I also welcome feedback and contributions from others experimenting with these approaches.

https://github.com/neviarrawlinson/governance-as-code
