"""Procedimentos do catálogo DeskGuard.

Cada módulo deste pacote pode registrar um procedimento com o decorador
`deskguard.catalog.registry.register`. O carregador em
`deskguard.catalog.loader` importa automaticamente todos os módulos
encontrados aqui, de modo que um novo procedimento entra no catálogo apenas
por ser criado como arquivo neste diretório.
"""
